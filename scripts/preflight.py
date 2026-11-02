#!/usr/bin/env python3
"""Checks that a live run is ready. Prints names and yes/no only, never secret values.
Run from the project folder:  .venv/bin/python scripts/preflight.py"""
import os, shutil, socket, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

problems, warnings = [], []
def check(ok, good, bad, hard=True):
    print(('  ok   ' if ok else ('  FAIL ' if hard else '  warn ')) + (good if ok else bad))
    if not ok: (problems if hard else warnings).append(bad)

print('Little Worlds preflight')
check(sys.version_info >= (3, 10), f'Python {sys.version.split()[0]}', 'Python 3.10 or newer is needed')
try:
    import websockets  # noqa: F401
    check(True, 'websockets installed (Twitch chat reading)', '')
except ImportError:
    check(False, '', 'websockets missing: run  .venv/bin/python -m pip install -r requirements.txt')
for name, why, hard in (('OPENAI_API_KEY', 'moderation and AI art', True), ('TWITCH_CLIENT_ID', 'Twitch sign-in', True),
                        ('TWITCH_CLIENT_SECRET', 'Twitch sign-in', True)):
    check(bool(os.environ.get(name, '').strip()), f'{name} is set', f'{name} is not set ({why})', hard)
check(os.environ.get('LITTLE_WORLDS_AI_ART') == '1', 'AI art is on', 'AI art is off (set LITTLE_WORLDS_AI_ART=1 for create, backgrounds and !draw art)', hard=False)
check(shutil.which('cloudflared') is not None, 'cloudflared is installed (remote viewers)', 'cloudflared not found: brew install cloudflared (only needed for remote viewers)', hard=False)
origin = os.environ.get('PUBLIC_VIEWER_ORIGIN', '').strip()
if origin:
    try:
        import server
        check(server.viewer_origin() != '', f'viewer link will use {server.viewer_origin()}', '', True)
    except ValueError as error:
        check(False, '', str(error))
else:
    check(False, '', 'PUBLIC_VIEWER_ORIGIN is not set: only people on this computer can join', hard=False)
for port in (8765, 8766):
    with socket.socket() as probe:
        busy = probe.connect_ex(('127.0.0.1', port)) == 0
    check(not busy, f'port {port} is free', f'port {port} is already in use: stop the old server first (Ctrl+C), restarting resets rooms', hard=(port == 8765))

print()
if problems: print(f'{len(problems)} problem(s) to fix before going live.'); sys.exit(1)
print('Ready.' + (f' {len(warnings)} optional item(s) above.' if warnings else ''))
