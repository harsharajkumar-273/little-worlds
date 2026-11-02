#!/usr/bin/env python3
"""Local-only, in-memory room server. No external dependencies."""
import base64
import hashlib
from collections import deque
import re
import json
import math
import os
import urllib.error
import urllib.request
import secrets
import string
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlencode, parse_qs

ROOT = Path(__file__).resolve().parent
ROOMS = {}
LOCK = threading.RLock()
OAUTH_STATES = {}
TWITCH_REDIRECT = "http://localhost:8765/twitch/callback"
MAX_BODY = 1_000_000
PREVIEW_LIMIT = 5
STYLES = {'neon': 'glowing neon sticker art', 'cartoon': 'a bold, colorful cartoon sticker illustration', 'pixel': 'crisp retro pixel art',
          'watercolor': 'a soft watercolor painting', 'storybook': 'a cozy storybook illustration'}
BEHAVIORS = {'still', 'float', 'sway', 'glow', 'rain'}

class Error(Exception):
    def __init__(self, status, message, **details): self.status, self.message, self.details = status, message, details

LIBRARY_LIMIT = 40
PLACEMENTS = ('object', 'backdrop', 'full')
THEMES = ('neon', 'space', 'sunset', 'forest', 'ocean', 'studio', 'green', 'clear')

def placement_of(data):
    kind = data.get('placement', 'object')
    if kind not in PLACEMENTS: raise Error(400, 'Invalid placement')
    return kind

def art_options(kind):
    """Full backgrounds are wide and opaque; objects and scenery pieces are square with a transparent background."""
    return ('1536x1024', 'opaque') if kind == 'full' else ('1024x1024', 'transparent')

def scale(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.4 <= value <= 4:
        raise Error(400, 'Invalid size')
    return value

def style_of(data):
    style = data.get('style', 'neon')
    if style not in STYLES: raise Error(400, 'Invalid style')
    return style

def position(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
        raise Error(400, 'Invalid position')
    return value

def room_for(code):
    room = ROOMS.get(code.upper())
    if not room: raise Error(404, 'Room not found')
    return room

def check_key(room, key):
    if not key or not secrets.compare_digest(room['key'], key): raise Error(403, 'Streamer access required')

def moderate_inputs(inputs):
    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not api_key: raise Error(503, 'Moderation is unavailable. Please try again later.')
    payload = json.dumps({'model': 'omni-moderation-latest', 'input': inputs}).encode()
    request = urllib.request.Request('https://api.openai.com/v1/moderations', data=payload,
        headers={'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=15) as response: result = json.load(response)
        flagged = result['results'][0]['flagged']
        if not isinstance(flagged, bool): raise ValueError('Invalid moderation result')
        return flagged
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        raise Error(503, 'Moderation is unavailable. Please try again later.') from None

def moderate(image, description, creator):
    return moderate_inputs([{'type': 'text', 'text': description}, {'type': 'text', 'text': creator},
                            {'type': 'image_url', 'image_url': {'url': image}}])

def moderate_text(description, creator):
    return moderate_inputs([{'type': 'text', 'text': description}, {'type': 'text', 'text': creator}])

def art_limit():
    """Image-generation attempts allowed per room, shared by previews, drawing polish and chat creation."""
    try: return max(1, int(os.environ.get('LITTLE_WORLDS_ART_LIMIT', '10')))
    except ValueError: return 10

def preview_key(image, description, style='neon'):
    return hashlib.sha256('\0'.join((image, description, style)).encode()).hexdigest()

def ai_art_enabled():
    return os.environ.get('LITTLE_WORLDS_AI_ART', '').strip() == '1' and bool(os.environ.get('OPENAI_API_KEY', '').strip())

def generate_art(image, description, style='neon', kind='object'):
    """Redraw the viewer's drawing as polished art. Returns a data URL, or None on any failure."""
    boundary = secrets.token_hex(16)
    size, background = art_options(kind)
    look = STYLES.get(style, STYLES['neon'])
    prompt = ('Redraw this hand-drawn sketch as a wide, full-frame background scene in ' + look + '. Fill the whole image edge to edge with no transparent areas and no text. '
              if kind == 'full' else 'Redraw this hand-drawn sketch as polished ' + look + ' on a transparent background. ') + \
             'Keep the same subject and composition. Subject described by the artist: ' + description
    fields = {'model': 'gpt-image-1.5', 'size': size, 'quality': 'low', 'background': background, 'output_format': 'webp', 'prompt': prompt}
    if kind == 'full': fields['output_compression'] = '50'  # wide opaque images are ~3 MB uncompressed; the scene is polled every second
    body = b''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="drawing.png"\r\nContent-Type: image/png\r\n\r\n').encode()
    body += base64.b64decode(image.partition(',')[2]) + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request('https://api.openai.com/v1/images/edits', data=body, method='POST', headers={
        'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'].strip(), 'Content-Type': 'multipart/form-data; boundary=' + boundary})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            encoded = json.load(response)['data'][0]['b64_json']
        if not isinstance(encoded, str) or len(encoded) > 1_500_000: return None
        base64.b64decode(encoded, validate=True)
        return 'data:image/webp;base64,' + encoded
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        detail = error.read(300).decode('utf-8', 'replace') if isinstance(error, urllib.error.HTTPError) else type(error).__name__
        print('AI art generation failed:', detail, flush=True)
        return None

def public(item):
    """Scene objects as other people may see them: never the original drawing."""
    return {k: v for k, v in item.items() if k != 'original'}

def preview(room, data, viewer_token):
    """Generate AI art for a viewer to look at privately. Nothing enters the review queue."""
    if not ai_art_enabled(): raise Error(409, 'AI art is not turned on for this room.')
    with LOCK:
        viewer = room['viewers'].get(viewer_token)
        if not viewer: raise Error(403, 'Please join the room again')
    with viewer['lock']:
        with LOCK:
            if viewer['warnings'] >= 3: raise Error(403, 'You are blocked from submitting for this room session.', warnings=viewer['warnings'])
            if room['paused']: raise Error(409, 'Submissions are paused')
            if viewer.get('previews', 0) >= PREVIEW_LIMIT: raise Error(429, f'You have used all {PREVIEW_LIMIT} AI previews. You can still send your drawing.', previews_left=0)
        image, description, creator = data.get('image'), data.get('description'), data.get('creator')
        create, style, kind = data.get('mode') == 'create', style_of(data), placement_of(data)
        extra = {'kind': kind} if kind != 'object' else {}
        if not create:
            if not isinstance(image, str) or not image.startswith('data:image/png;base64,') or len(image) > 800_000: raise Error(400, 'Invalid drawing')
            try:
                if not base64.b64decode(image.partition(',')[2], validate=True).startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError()
            except (ValueError, TypeError): raise Error(400, 'Invalid drawing')
        if not isinstance(description, str) or not description.strip() or len(description) > 200: raise Error(400, 'Please describe what you want in 200 characters or fewer')
        if not isinstance(creator, str) or not creator.strip() or len(creator.strip()) > 25 or any(ord(c) < 32 or ord(c) == 127 for c in creator): raise Error(400, 'Enter a display name of 1 to 25 characters')
        description, creator = description.strip(), creator.strip()
        def blocked():
            with LOCK:
                viewer['warnings'] += 1
                message = f'This was blocked by moderation. Warning {viewer["warnings"]} of 3.'
                if viewer['warnings'] >= 3: message += ' You are blocked from submitting for this room session.'
                return Error(403, message, warnings=viewer['warnings'])
        if (moderate_text(description, creator) if create else moderate(image, description, creator)): raise blocked()
        with LOCK:
            if room['chat_attempts'] >= art_limit(): raise Error(429, 'This room has reached its AI art limit. You can still send your drawing.')
            room['chat_attempts'] += 1
            viewer['previews'] = viewer.get('previews', 0) + 1
            left = PREVIEW_LIMIT - viewer['previews']
        if create:
            try: art = generate_chat_art(description, style, **extra)
            except Error: art = None
        else: art = generate_art(image, description, style, **extra)
        if not art: raise Error(503, 'AI art could not be made right now. Please try again.', previews_left=left)
        if moderate(art, description, creator): raise blocked()
        with LOCK: viewer['preview'] = (preview_key('create' if create else image, description, f'{style}:{kind}'), art)
        return {'art': art, 'previews_left': left}

def submit(room, data, viewer_token):
    with LOCK:
        viewer = room['viewers'].get(viewer_token)
        if not viewer: raise Error(403, 'Please join the room again')
    # Serialize each viewer's requests so concurrent submissions cannot bypass warning limits.
    with viewer['lock']:
        with LOCK:
            if viewer['warnings'] >= 3: raise Error(403, 'You are blocked from submitting for this room session.', warnings=viewer['warnings'])
            if room['paused']: raise Error(409, 'Submissions are paused')
        image, behavior, description, creator = data.get('image'), data.get('behavior'), data.get('description'), data.get('creator')
        create, style, kind = data.get('mode') == 'create', style_of(data), placement_of(data)
        extra = {'kind': kind} if kind != 'object' else {}
        if create:
            # Created from text: only a preview this viewer already saw (and that was moderated) can be sent.
            stored = viewer.get('preview')
            if not isinstance(description, str) or not stored or stored[0] != preview_key('create', description.strip(), f'{style}:{kind}'):
                raise Error(400, 'Preview your AI creation first, then send it.')
            image = stored[1]
        else:
            if not isinstance(image, str) or not image.startswith('data:image/png;base64,') or len(image) > 800_000: raise Error(400, 'Invalid drawing')
            try:
                raw = base64.b64decode(image.partition(',')[2], validate=True)
                if not raw.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError()
            except (ValueError, TypeError): raise Error(400, 'Invalid drawing')
        if not isinstance(behavior, str) or behavior not in BEHAVIORS: raise Error(400, 'Invalid behavior')
        if not isinstance(description, str) or not description.strip() or len(description) > 200: raise Error(400, 'Please describe your drawing in 200 characters or fewer')
        if not isinstance(creator, str) or not creator.strip() or len(creator.strip()) > 25 or any(ord(c) < 32 or ord(c) == 127 for c in creator): raise Error(400, 'Enter a display name of 1 to 25 characters')
        creator = creator.strip()
        x, y = position(data.get('x')), position(data.get('y'))
        description = description.strip()
        flagged = moderate(image, description, creator)
        art = None
        if not flagged and not create and ai_art_enabled() and data.get('polish', True) is not False:
            # A preview the viewer already saw was moderated when it was made; reuse it instead of generating again.
            stored = viewer.get('preview')
            if stored and stored[0] == preview_key(image, description, f'{style}:{kind}'): art = stored[1]
            # All generation paths share the room's attempt limit.
            with LOCK:
                can_generate = art is None and not room['paused'] and room['chat_attempts'] < art_limit()
                if can_generate: room['chat_attempts'] += 1
            if can_generate:
                art = generate_art(image, description, style, **extra)
                try:
                    if art and moderate(art, description, creator): art = None
                except Error: art = None
        with LOCK:
            if flagged:
                viewer['warnings'] += 1
                count = viewer['warnings']
                message = f'This submission was blocked by moderation. Warning {count} of 3.'
                if count >= 3: message += ' You are blocked from submitting for this room session.'
                raise Error(403, message, warnings=count)
            if room['paused']: raise Error(409, 'Submissions are paused')
            item = {'id': room['next'], 'image': image, 'description': description, 'creator': creator, 'behavior': 'still' if kind == 'full' else behavior, 'x': 50 if kind == 'full' else x, 'y': 50 if kind == 'full' else y,
                    'scale': 2.0 if kind == 'backdrop' else 1.0, 'placement': kind, 'ai': create}
            if art:
                item.update(image=art, original=image, ai=True)
            room['next'] += 1
            room['pending'].append(item)
            return {'ok': True, 'warnings': viewer['warnings']}

def library_add(room, item):
    """Remember what the streamer approved or made so it can be reused as a background later. Caller holds LOCK."""
    library = room.setdefault('library', [])
    if any(x['id'] == item['id'] for x in library): return
    library.append({'id': item['id'], 'image': item['image'], 'description': item.get('description', ''), 'creator': item.get('creator', ''),
                    'placement': item.get('placement', 'object'), 'ai': bool(item.get('ai'))})
    del library[:-LIBRARY_LIMIT]

def library_use(room, item_id, action, data):
    """Streamer-only: put a saved creation back in the scene as the full background or as a background piece, or forget it."""
    with LOCK:
        entry = next((x for x in room.get('library', []) if str(x['id']) == item_id), None)
        if entry is None: raise Error(404, 'That is not in your library')
        if action == 'delete':
            room['library'].remove(entry); return {'ok': True}
        if action != 'use': raise Error(404, 'Not found')
        kind = data.get('as')
        if kind not in ('full', 'piece'): raise Error(400, 'Choose full background or background piece')
        placement = 'full' if kind == 'full' else 'backdrop'
        item = {'id': room['next'], 'image': entry['image'], 'description': entry['description'], 'creator': entry['creator'], 'behavior': 'still',
                'x': 50, 'y': 50, 'scale': 2.0 if placement == 'backdrop' else 1.0, 'placement': placement, 'ai': entry['ai'], 'source': 'library'}
        room['next'] += 1
        if placement == 'full': room['approved'][:] = [x for x in room['approved'] if x.get('placement') != 'full']
        room['approved'].append(item)
        return {'ok': True}

def background(room, action, data):
    """Streamer-only: create, apply or clear a custom full background. The streamer decides, so there is no approval queue."""
    if action == 'clear':
        with LOCK: room['approved'][:] = [x for x in room['approved'] if x.get('placement') != 'full']
        return {'ok': True}
    if action == 'create':
        if not ai_art_enabled(): raise Error(409, 'AI art is not turned on.')
        description, style = data.get('description'), style_of(data)
        if not isinstance(description, str) or not description.strip() or len(description) > 200:
            raise Error(400, 'Describe the background in 200 characters or fewer')
        description = description.strip()
        if moderate_text(description, 'Streamer'): raise Error(403, 'That description was blocked by moderation.')
        with LOCK:
            if room['chat_attempts'] >= art_limit(): raise Error(429, 'This room has reached its AI art limit.')
            room['chat_attempts'] += 1
        art = generate_chat_art(description, style, kind='full')
        if moderate(art, description, 'Streamer'): raise Error(403, 'The picture was blocked by moderation.')
        with LOCK: room['background_preview'] = art
        return {'art': art}
    if action == 'apply':
        if data.get('use') == 'preview':
            with LOCK: image = room.get('background_preview')
            if not image: raise Error(400, 'Create a background first.')
            ai, text = True, 'AI background'
        else:
            image, ai, text = data.get('image'), False, 'Uploaded background'
            match = isinstance(image, str) and re.match(r'data:image/(png|jpeg|webp);base64,', image)
            if not match or len(image) > 900_000: raise Error(400, 'Choose a PNG, JPEG or WebP image under about 650 KB.')
            try: raw = base64.b64decode(image[match.end():], validate=True)
            except (ValueError, TypeError): raise Error(400, 'Invalid image')
            signatures = {'png': raw.startswith(b'\x89PNG\r\n\x1a\n'), 'jpeg': raw.startswith(b'\xff\xd8\xff'), 'webp': raw[:4] == b'RIFF' and raw[8:12] == b'WEBP'}
            if not signatures[match.group(1)]: raise Error(400, 'Invalid image')
        with LOCK:
            item = {'id': room['next'], 'image': image, 'description': text, 'creator': 'Streamer', 'behavior': 'still', 'x': 50, 'y': 50,
                    'scale': 1.0, 'placement': 'full', 'ai': ai, 'source': 'streamer'}
            room['next'] += 1
            room['approved'][:] = [x for x in room['approved'] if x.get('placement') != 'full'] + [item]
            library_add(room, item)
        return {'ok': True}
    raise Error(404, 'Not found')

def twitch_config():
    client_id = os.environ.get('TWITCH_CLIENT_ID', '').strip()
    client_secret = os.environ.get('TWITCH_CLIENT_SECRET', '').strip()
    if not client_id or not client_secret:
        raise Error(503, 'Twitch is not configured. Set the Twitch client ID and secret on the server.')
    return client_id, client_secret

def twitch_request(url, *, form=None, token=None, client_id=None, json_body=None):
    headers = {'Accept': 'application/json'}
    data = None
    if form is not None:
        data = urlencode(form).encode(); headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if json_body is not None:
        data = json.dumps(json_body).encode(); headers['Content-Type'] = 'application/json'
    if token: headers['Authorization'] = 'Bearer ' + token
    if client_id: headers['Client-Id'] = client_id
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except (OSError, ValueError, TypeError) as error:
        # Log only the endpoint path and Twitch's own error text; never tokens, headers or request bodies.
        detail = error.read(200).decode('utf-8', 'replace') if isinstance(error, urllib.error.HTTPError) else type(error).__name__
        print('Twitch request failed:', urlsplit(url).path, getattr(error, 'code', ''), detail, flush=True)
        raise Error(503, 'Twitch request failed. Please reconnect or try again.') from None

def twitch_start(room):
    client_id, _ = twitch_config()
    state = secrets.token_urlsafe(32)
    with LOCK:
        now = time.monotonic()
        for old, value in list(OAUTH_STATES.items()):
            if value['expires'] < now: OAUTH_STATES.pop(old, None)
        OAUTH_STATES[state] = {'room': room, 'expires': now + 600}
    params = {'client_id': client_id, 'redirect_uri': TWITCH_REDIRECT,
              'response_type': 'code', 'scope': 'user:read:chat user:write:chat', 'state': state}
    return {'url': 'https://id.twitch.tv/oauth2/authorize?' + urlencode(params)}

def twitch_callback(state, code):
    with LOCK: saved = OAUTH_STATES.pop(state, None)
    if not saved or saved['expires'] < time.monotonic() or not code:
        raise Error(400, 'Twitch authorization expired or was declined. Return to the streamer window and try again.')
    client_id, secret = twitch_config()
    tokens = twitch_request('https://id.twitch.tv/oauth2/token', form={
        'client_id': client_id, 'client_secret': secret, 'code': code,
        'grant_type': 'authorization_code', 'redirect_uri': TWITCH_REDIRECT})
    if not isinstance(tokens.get('access_token'), str) or not isinstance(tokens.get('refresh_token'), str):
        raise Error(503, 'Twitch did not return a complete authorization. Please reconnect.')
    validation = twitch_request('https://id.twitch.tv/oauth2/validate', token=tokens['access_token'])
    if validation.get('client_id') != client_id or not {'user:read:chat', 'user:write:chat'}.issubset(validation.get('scopes', [])) or not validation.get('user_id'):
        raise Error(403, 'Twitch authorization could not be verified.')
    twitch = {'access_token': tokens['access_token'], 'refresh_token': tokens['refresh_token'],
              'user_id': validation['user_id'], 'login': validation.get('login', ''), 'announcements': False}
    with LOCK: saved['room']['twitch'] = twitch

def twitch_token(room):
    # Caller holds the room's Twitch lock while validating or refreshing tokens.
    with LOCK: twitch = room.get('twitch')
    if not twitch: raise Error(409, 'Connect Twitch first.')
    client_id, secret = twitch_config()
    try:
        valid = twitch_request('https://id.twitch.tv/oauth2/validate', token=twitch['access_token'])
    except Error:
        tokens = twitch_request('https://id.twitch.tv/oauth2/token', form={
            'grant_type': 'refresh_token', 'refresh_token': twitch['refresh_token'],
            'client_id': client_id, 'client_secret': secret})
        if not tokens.get('access_token') or not tokens.get('refresh_token'):
            raise Error(503, 'Twitch authorization expired. Please reconnect.')
        valid = twitch_request('https://id.twitch.tv/oauth2/validate', token=tokens['access_token'])
        if valid.get('client_id') != client_id or valid.get('user_id') != twitch['user_id'] or not {'user:read:chat', 'user:write:chat'}.issubset(valid.get('scopes', [])):
            raise Error(403, 'Twitch authorization could not be verified.')
        twitch['access_token'], twitch['refresh_token'] = tokens['access_token'], tokens['refresh_token']
    if valid.get('client_id') != client_id or valid.get('user_id') != twitch['user_id'] or not {'user:read:chat', 'user:write:chat'}.issubset(valid.get('scopes', [])):
        raise Error(403, 'Twitch authorization could not be verified. Please reconnect.')
    return twitch, client_id

def twitch_send(room, message):
    with room['twitch_lock']:
        twitch, client_id = twitch_token(room)
        response = twitch_request('https://api.twitch.tv/helix/chat/messages', token=twitch['access_token'],
            client_id=client_id, json_body={'broadcaster_id': twitch['user_id'], 'sender_id': twitch['user_id'], 'message': message})
        if not response.get('data') or not response['data'][0].get('is_sent'):
            raise Error(503, 'Twitch did not send the message. Check chat settings and try again.')

def generate_chat_art(prompt, style=None, kind='object'):
    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not api_key: raise Error(503, 'Image generation is unavailable.')
    size, background = art_options(kind)
    if not style: lead = 'Create one isolated streamer scene object on a transparent background: '
    elif kind == 'full': lead = 'Create a wide, full-frame background scene as ' + STYLES[style] + ', filling the whole image edge to edge with no text: '
    elif kind == 'backdrop': lead = 'Create one piece of scenery (such as a building, tree, hill or sign) as ' + STYLES[style] + ' on a transparent background: '
    else: lead = 'Create one isolated scene object as ' + STYLES[style] + ' on a transparent background: '
    options = {'model':'gpt-image-1.5', 'size':size, 'quality':'low', 'background':background, 'output_format':'webp', 'prompt': lead + prompt}
    if kind == 'full': options['output_compression'] = 50  # wide opaque images are ~3 MB uncompressed; the scene is polled every second
    request = urllib.request.Request('https://api.openai.com/v1/images/generations', method='POST',
        headers={'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}, data=json.dumps(options).encode())
    try:
        with urllib.request.urlopen(request, timeout=90) as response: encoded = json.load(response)['data'][0]['b64_json']
        if not isinstance(encoded, str) or len(encoded) > 1_500_000: raise ValueError()
        raw = base64.b64decode(encoded, validate=True)
        if not raw.startswith(b'RIFF') or raw[8:12] != b'WEBP': raise ValueError()
        return 'data:image/webp;base64,' + encoded
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        detail = error.read(300).decode('utf-8', 'replace') if isinstance(error, urllib.error.HTTPError) else type(error).__name__
        print('Image generation failed:', detail, flush=True)
        raise Error(503, 'Image generation is unavailable.') from None

def chat_command(room, event, message_id):
    """Process a single Twitch event; caller runs this off the EventSub listener."""
    text = event.get('message', {}).get('text', '')
    user_id, creator = event.get('chatter_user_id'), event.get('chatter_user_name')
    if not isinstance(text, str) or not text.startswith('!draw '): return
    prompt = text[6:].strip()
    if not prompt or len(prompt) > 200 or not isinstance(user_id, str) or not user_id or not isinstance(creator, str) or not creator or len(creator) > 25: return
    with LOCK:
        if not room['chat_enabled'] or room['paused'] or not message_id or message_id in room['chat_seen']: return
        room['chat_seen'].add(message_id)
        viewer = room['chat_users'].setdefault(user_id, {'warnings':0, 'next_at':0, 'lock':threading.Lock()})
    with viewer['lock']:
        with LOCK:
            if not room['chat_enabled'] or room['paused'] or viewer['warnings'] >= 3 or time.monotonic() < viewer['next_at']: return
            viewer['next_at'] = time.monotonic() + 60
        try:
            if moderate_text(prompt, creator):
                with LOCK:
                    viewer['warnings'] += 1
                    room['chat_status'] = f'{creator}: submission blocked (warning {viewer["warnings"]} of 3).'
                return
            with LOCK:
                if not room['chat_enabled'] or room['paused'] or room['chat_attempts'] >= art_limit(): return
                room['chat_attempts'] += 1
            image = generate_chat_art(prompt)
            if moderate(image, prompt, creator):
                with LOCK:
                    viewer['warnings'] += 1
                    room['chat_status'] = f'{creator}: submission blocked (warning {viewer["warnings"]} of 3).'
                return
            with LOCK:
                if not room['chat_enabled'] or room['paused']: return
                item = {'id': room['next'], 'image': image, 'description': prompt, 'creator': creator,
                        'behavior':'still', 'x':22, 'y':32, 'scale':1.0, 'ai':True, 'source':'twitch'}
                room['next'] += 1; room['pending'].append(item)
        except Error:
            with LOCK: room['chat_status'] = 'A creation could not be processed; check service configuration.'

def eventsub_loop(room):
    """Listen to channel.chat.message over Twitch's local-client WebSocket."""
    try:
        from websockets.sync.client import connect
        url = 'wss://eventsub.wss.twitch.tv/ws'
        migrating = False
        while True:
            with LOCK:
                if not room['chat_enabled']: break
                room['chat_status'] = 'connecting'
            try:
                with connect(url, open_timeout=10, close_timeout=2, max_size=1_000_000) as ws:
                    reconnect = None
                    while True:
                        with LOCK:
                            if not room['chat_enabled']: break
                        try: raw = ws.recv(timeout=2)
                        except TimeoutError: continue
                        payload = json.loads(raw)
                        metadata, detail = payload.get('metadata', {}), payload.get('payload', {})
                        kind = metadata.get('message_type')
                        if kind == 'session_welcome':
                            if not migrating:
                                with room['twitch_lock']:
                                    twitch, client_id = twitch_token(room)
                                    twitch_request('https://api.twitch.tv/helix/eventsub/subscriptions', token=twitch['access_token'], client_id=client_id, json_body={
                                        'type':'channel.chat.message','version':'1','condition':{'broadcaster_user_id':twitch['user_id'],'user_id':twitch['user_id']},
                                        'transport':{'method':'websocket','session_id':detail['session']['id']}})
                            migrating = False
                            with LOCK: room['chat_status'] = 'listening'
                        elif kind == 'notification' and detail.get('subscription', {}).get('type') == 'channel.chat.message':
                            event = detail.get('event', {})
                            with LOCK: connected_user = room['twitch']['user_id'] if room['twitch'] else None
                            if event.get('broadcaster_user_id') == connected_user and event.get('message', {}).get('text', '').startswith('!draw '):
                                threading.Thread(target=chat_command, args=(room, event, metadata.get('message_id')), daemon=True).start()
                        elif kind == 'session_reconnect':
                            candidate = detail.get('session', {}).get('reconnect_url', '')
                            parsed = urlsplit(candidate)
                            if parsed.scheme == 'wss' and parsed.hostname == 'eventsub.wss.twitch.tv': reconnect = candidate
                            break
                        elif kind == 'revocation':
                            with LOCK: room['chat_status'] = 'Twitch chat subscription revoked; reconnect Twitch.'; room['chat_enabled'] = False
                            break
                    if reconnect: url, migrating = reconnect, True
                    else: url, migrating = 'wss://eventsub.wss.twitch.tv/ws', False
            except Exception as error:
                print('EventSub connection error:', type(error).__name__, getattr(error, 'message', ''), flush=True)
                with LOCK:
                    if not room['chat_enabled']: break
                    room['chat_status'] = 'Twitch chat disconnected; retrying.'
                time.sleep(3); url, migrating = 'wss://eventsub.wss.twitch.tv/ws', False
    except ImportError:
        with LOCK: room['chat_status'] = 'Install the WebSocket dependency to enable chat.'; room['chat_enabled'] = False
    finally:
        with LOCK: room['chat_worker'] = False


def approve(room, action, item_id):
    with LOCK:
        item = next((x for x in room['pending'] if str(x['id']) == item_id), None)
        if item is None: raise Error(404, 'Submission not found')
        room['pending'].remove(item)
        if action == 'approve':
            if item.get('placement') == 'full': room['approved'][:] = [x for x in room['approved'] if x.get('placement') != 'full']
            room['approved'].append(item)
            library_add(room, item)
        announce = action == 'approve' and bool(room.get('twitch') and room['twitch']['announcements'])
    if announce:
        try: twitch_send(room, 'A community creation was approved and added to the scene!')
        except Error: return {'ok': True, 'chat_error': 'Approved, but the Twitch announcement could not be sent.'}
    return {'ok': True}

def viewer_origin():
    value = os.environ.get('PUBLIC_VIEWER_ORIGIN', '').strip().lower()
    if not value: return ''
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or
        not re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com', parsed.hostname) or
        parsed.netloc != parsed.hostname or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('PUBLIC_VIEWER_ORIGIN must be an HTTPS Quick Tunnel origin, such as https://example.trycloudflare.com')
    return 'https://' + parsed.hostname

def viewer_link(code):
    origin = viewer_origin()
    return origin + '/?room=' + code if origin else ''

def public_api_allowed(method, path):
    parts = path.strip('/').split('/')
    if len(parts) < 3 or parts[:2] != ['api', 'rooms'] or not re.fullmatch(r'[A-Z2-9]{6}', parts[2]): return False
    tail = parts[3:]
    return (method == 'GET' and tail in ([], ['viewer'])) or (method == 'POST' and tail in (['join'], ['submissions'], ['preview']))

def public_rate_check(http_server, path):
    parts = path.strip('/').split('/')
    now = time.monotonic()
    with LOCK:
        all_events = http_server.public_events
        while all_events and all_events[0] <= now - 60: all_events.popleft()
        if len(all_events) >= 120: raise Error(429, 'Too many requests. Please try again shortly.')
        all_events.append(now)
        room = ROOMS.get(parts[2])
        if not room: return
        kind = parts[3]
        events = room['public_rates'][kind]
        while events and events[0] <= now - 60: events.popleft()
        limit = 20 if kind == 'join' else 10
        if len(events) >= limit: raise Error(429, 'Room is busy. Please try again shortly.')
        if kind == 'submissions' and len(room['pending']) >= 50: raise Error(429, 'Review queue is full. Please try again later.')
        events.append(now)

def dispatch(method, path, data=None, key='', viewer_token=''):
    data = data if isinstance(data, dict) else {}
    parts = path.strip('/').split('/')
    if method == 'POST' and len(parts) == 4 and parts[:2] == ['api', 'rooms'] and parts[3] == 'submissions':
        with LOCK: room = room_for(parts[2])
        return submit(room, data, viewer_token)
    if method == 'POST' and len(parts) == 4 and parts[:2] == ['api', 'rooms'] and parts[3] == 'preview':
        with LOCK: room = room_for(parts[2])
        return preview(room, data, viewer_token)
    if method == 'POST' and len(parts) == 5 and parts[:2] == ['api', 'rooms'] and parts[3] == 'background':
        with LOCK:
            room = room_for(parts[2]); check_key(room, key)
        return background(room, parts[4], data)
    if method == 'POST' and len(parts) == 5 and parts[:2] == ['api', 'rooms'] and parts[3] in ('approve', 'reject'):
        with LOCK:
            room = room_for(parts[2]); check_key(room, key)
        return approve(room, parts[3], parts[4])
    if method == 'POST' and len(parts) == 5 and parts[:2] == ['api', 'rooms'] and parts[3:] == ['twitch', 'share']:
        with LOCK:
            room = room_for(parts[2]); check_key(room, key)
        link = viewer_link(parts[2].upper())
        message = f'Join our Little Worlds room: {link}' if link else f'Little Worlds local test: room code {parts[2].upper()}. This room is only available on the streamer’s computer.'
        twitch_send(room, message)
        return {'ok': True}
    with LOCK:
        if method == 'POST' and parts == ['api', 'rooms']:
            alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
            while True:
                code = ''.join(secrets.choice(alphabet) for _ in range(6))
                if code not in ROOMS: break
            token = secrets.token_urlsafe(32)
            ROOMS[code] = {'key': token, 'pending': [], 'approved': [], 'paused': False, 'theme': 'neon', 'next': 1, 'viewers': {}, 'twitch': None, 'twitch_lock': threading.Lock(), 'chat_enabled': False, 'chat_status': 'off', 'chat_attempts': 0, 'chat_users': {}, 'chat_seen': set(), 'chat_worker': False, 'public_rates': {'join': deque(), 'submissions': deque(), 'preview': deque()}}
            return {'code': code, 'key': token}
        if len(parts) < 3 or parts[:2] != ['api', 'rooms']: raise Error(404, 'Not found')
        room = room_for(parts[2])
        action = parts[3:]
        if method == 'GET' and not action:
            return {'approved': [public(x) for x in room['approved']], 'paused': room['paused'], 'theme': room['theme']}
        if method == 'GET' and action == ['review']:
            check_key(room, key)
            return {'approved': [public(x) for x in room['approved']], 'pending': [dict(x) for x in room['pending']], 'paused': room['paused'], 'theme': room['theme'], 'viewer_url': viewer_link(parts[2]), 'library': [{k: v for k, v in x.items() if k != 'image'} for x in room.get('library', [])], 'chat_creation': {'enabled': room['chat_enabled'], 'status': room['chat_status'], 'attempts': room['chat_attempts'], 'limit': art_limit()}, 'twitch': {'connected': bool(room['twitch']), 'login': room['twitch']['login'] if room['twitch'] else '', 'announcements': room['twitch']['announcements'] if room['twitch'] else False}}
        if method == 'POST' and action == ['join']:
            # A token is stable only for this tab session and can be reset by a viewer.
            token = viewer_token if viewer_token in room['viewers'] else secrets.token_urlsafe(32)
            if token not in room['viewers']: room['viewers'][token] = {'warnings': 0, 'lock': threading.Lock()}
            return {'viewer_token': token, 'warnings': room['viewers'][token]['warnings'], 'ai_art': ai_art_enabled()}
        if method == 'GET' and action == ['viewer']:
            viewer = room['viewers'].get(viewer_token)
            if not viewer: raise Error(403, 'Please join the room again')
            return {'warnings': viewer['warnings']}
        check_key(room, key)
        if action[:1] == ['library'] and method == 'GET' and len(action) == 2:
            entry = next((x for x in room.get('library', []) if str(x['id']) == action[1]), None)
            if entry is None: raise Error(404, 'That is not in your library')
            return {'image': entry['image']}
        if action[:1] == ['library'] and method == 'POST' and len(action) == 3:
            return library_use(room, action[1], action[2], data)
        if method == 'POST' and action == ['twitch', 'start']:
            return twitch_start(room)
        if method == 'POST' and action == ['twitch', 'announcements']:
            if not isinstance(data.get('enabled'), bool): raise Error(400, 'Invalid announcement setting')
            if not room['twitch']: raise Error(409, 'Connect Twitch first.')
            room['twitch']['announcements'] = data['enabled']; return {'ok': True}
        if method == 'POST' and action == ['chat', 'toggle']:
            if not isinstance(data.get('enabled'), bool): raise Error(400, 'Invalid chat setting')
            if data['enabled'] and not room['twitch']: raise Error(409, 'Connect Twitch first.')
            room['chat_enabled'] = data['enabled']
            if data['enabled'] and not room['chat_worker']:
                room['chat_worker'] = True
                threading.Thread(target=eventsub_loop, args=(room,), daemon=True).start()
            if not data['enabled']: room['chat_status'] = 'off'
            return {'ok': True}
        if method == 'POST' and action == ['theme']:
            theme = data.get('theme')
            if theme not in THEMES: raise Error(400, 'Invalid theme')
            # Choosing a preset replaces any custom full background, like picking a new background in a video call.
            room['approved'][:] = [x for x in room['approved'] if x.get('placement') != 'full']
            room['theme'] = theme; return {'ok': True}
        if method == 'POST' and action == ['pause']:
            if not isinstance(data.get('paused'), bool): raise Error(400, 'Invalid pause state')
            room['paused'] = data['paused']; return {'ok': True}
        if method == 'POST' and action == ['clear']:
            room['approved'].clear(); return {'ok': True}
        if method == 'POST' and len(action) == 2 and action[0] == 'placement':
            item = next((x for x in room['pending'] if str(x['id']) == action[1]), None)
            if item is None: raise Error(404, 'Submission not found')
            if 'x' in data or 'y' in data: item.update(x=position(data.get('x')), y=position(data.get('y')))
            if 'scale' in data: item['scale'] = scale(data['scale'])
            return {'ok': True}
        if len(action) == 2 and action[0] == 'objects' and method in ('POST', 'DELETE'):
            item = next((x for x in room['approved'] if str(x['id']) == action[1]), None)
            if item is None: raise Error(404, 'Object not found')
            if method == 'DELETE': room['approved'].remove(item)
            else:
                if 'x' in data or 'y' in data: item.update(x=position(data.get('x')), y=position(data.get('y')))
                if 'scale' in data: item['scale'] = scale(data['scale'])
            return {'ok': True}
        raise Error(404, 'Not found')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # OAuth callback URLs contain short-lived secrets; never log the request path.
        if urlsplit(self.path).path == '/twitch/callback': return
        super().log_message(format, *args)
    def send_json(self, status, value):
        payload = json.dumps(value, separators=(',', ':')).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def handle_request(self):
        path = urlsplit(self.path).path
        viewer_only = getattr(self.server, 'viewer_only', False)
        if viewer_only:
            try:
                origin = self.server.viewer_origin
                if self.headers.get('Host', '').lower() != urlsplit(origin).netloc: raise Error(403, 'Invalid host')
                request_origin = self.headers.get('Origin')
                if request_origin and request_origin != origin: raise Error(403, 'Cross-origin request denied')
                if self.command == 'POST' and request_origin != origin: raise Error(403, 'Origin required')
                if self.headers.get('X-Streamer-Key'): raise Error(403, 'Streamer access is local only')
                static_allowed = self.command == 'GET' and path in ('/', '/index.html', '/app.js', '/style.css', '/cutout.js', '/promptkit.js')
                if not static_allowed and not public_api_allowed(self.command, path): raise Error(403, 'Viewer access only')
                if self.command == 'POST': public_rate_check(self.server, path)
            except Error as e:
                self.send_json(e.status, {'error': e.message, **e.details}); return
        if path == '/twitch/callback' and self.command == 'GET':
            try:
                if self.headers.get('Host') != f'localhost:{self.server.server_port}': raise Error(403, 'Invalid callback host')
                params = parse_qs(urlsplit(self.path).query)
                twitch_callback(params.get('state', [''])[0], params.get('code', [''])[0])
                message = 'Twitch connected. You can close this tab and return to the streamer window.'
                status = 200
            except Error as e:
                message = e.message; status = e.status
            content = message.encode('utf-8')
            self.send_response(status); self.send_header('Content-Type', 'text/plain; charset=utf-8'); self.send_header('Cache-Control', 'no-store'); self.send_header('Referrer-Policy', 'no-referrer'); self.send_header('Content-Length', str(len(content))); self.end_headers(); self.wfile.write(content); return
        if path.startswith('/api/'):
            try:
                if not viewer_only:
                    origin = self.headers.get('Origin')
                    expected = f'http://{self.headers.get("Host", "")}'
                    if origin and origin != expected: raise Error(403, 'Cross-origin request denied')
                    if self.headers.get('Host') not in (f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}'): raise Error(403, 'Invalid host')
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0 or length > MAX_BODY: raise Error(413, 'Request too large')
                data = json.loads(self.rfile.read(length)) if length else {}
                result = dispatch(self.command, path, data, self.headers.get('X-Streamer-Key', ''), self.headers.get('X-Viewer-Token', ''))
                self.send_json(200, result)
            except Error as e: self.send_json(e.status, {'error': e.message, **e.details})
            except (ValueError, UnicodeDecodeError): self.send_json(400, {'error': 'Invalid request'})
            return
        files = {
            '/': ('index.html', 'text/html; charset=utf-8'),
            '/index.html': ('index.html', 'text/html; charset=utf-8'),
            '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
            '/output': ('output.html', 'text/html; charset=utf-8'),
            '/output.js': ('output.js', 'text/javascript; charset=utf-8'),
            '/style.css': ('style.css', 'text/css; charset=utf-8'),
            '/cutout.js': ('cutout.js', 'text/javascript; charset=utf-8'),
            '/promptkit.js': ('promptkit.js', 'text/javascript; charset=utf-8'),
            # Person-cutout model for the streamer's webcam preview. Not served on the public viewer port.
            '/vendor/mediapipe/vision_bundle.mjs': ('vendor/mediapipe/vision_bundle.mjs', 'text/javascript; charset=utf-8'),
            '/vendor/mediapipe/wasm/vision_wasm_internal.js': ('vendor/mediapipe/wasm/vision_wasm_internal.js', 'text/javascript; charset=utf-8'),
            '/vendor/mediapipe/wasm/vision_wasm_internal.wasm': ('vendor/mediapipe/wasm/vision_wasm_internal.wasm', 'application/wasm'),
            '/vendor/mediapipe/selfie_segmenter.tflite': ('vendor/mediapipe/selfie_segmenter.tflite', 'application/octet-stream'),
        }
        if self.command != 'GET' or path not in files: self.send_error(404); return
        name, mime = files[path]; content = (ROOT / name).read_bytes()
        if viewer_only and name == 'index.html': content = content.replace(b'<body>', b'<body data-viewer-only="true">', 1)
        self.send_response(200); self.send_header('Content-Type', mime); self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(content))); self.end_headers(); self.wfile.write(content)
    do_GET = handle_request
    do_POST = handle_request
    do_DELETE = handle_request

def main():
    try: origin = viewer_origin()
    except ValueError as error:
        print(str(error), flush=True); return
    server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    viewer = None
    try:
        if origin:
            viewer = ThreadingHTTPServer(('127.0.0.1', 8766), Handler)
            viewer.viewer_only = True
            viewer.viewer_origin = origin
            viewer.public_events = deque()
            threading.Thread(target=viewer.serve_forever, daemon=True).start()
            print('Viewer-only endpoint ready on 127.0.0.1:8766. No tunnel is started.', flush=True)
        print('Streamer controls: http://127.0.0.1:8765', flush=True)
        server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if viewer: viewer.shutdown(); viewer.server_close()
        server.server_close()

if __name__ == '__main__': main()
