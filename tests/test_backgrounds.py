import base64
import os
import unittest
from unittest.mock import patch
import server

ART = 'data:image/webp;base64,' + base64.b64encode(b'RIFFxxxxWEBPwide').decode()
PNG = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nbody').decode()
JPEG = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xffbody').decode()

class BackgroundTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        room = server.dispatch('POST', '/api/rooms')
        self.path, self.key = '/api/rooms/' + room['code'], room['key']
        env = patch.dict(os.environ, {'LITTLE_WORLDS_AI_ART': '1', 'OPENAI_API_KEY': 'test', 'LITTLE_WORLDS_ART_LIMIT': '50'})
        env.start(); self.addCleanup(env.stop)

    def bg(self, name, body=None, key=None):
        return server.dispatch('POST', self.path + '/background/' + name, body or {}, self.key if key is None else key)

    def state(self): return server.dispatch('GET', self.path)
    def fulls(self): return [x for x in self.state()['approved'] if x['placement'] == 'full']

    def make_ai(self, words='a cozy attic'):
        with patch('server.moderate_text', return_value=False), patch('server.moderate', return_value=False), \
                patch('server.generate_chat_art', return_value=ART) as generate:
            result = self.bg('create', {'description': words, 'style': 'storybook'})
        return result, generate

    def test_every_preset_theme_is_accepted_and_junk_is_not(self):
        for theme in server.THEMES:
            server.dispatch('POST', self.path + '/theme', {'theme': theme}, self.key)
            self.assertEqual(self.state()['theme'], theme)
        with self.assertRaises(server.Error): server.dispatch('POST', self.path + '/theme', {'theme': 'lava'}, self.key)

    def test_ai_background_is_made_wide_then_applied_without_a_queue(self):
        result, generate = self.make_ai()
        generate.assert_called_once_with('a cozy attic', 'storybook', kind='full')
        self.assertEqual(result, {'art': ART})
        self.assertEqual(self.fulls(), [])
        self.bg('apply', {'use': 'preview'})
        item, = self.fulls()
        self.assertEqual((item['image'], item['creator'], item['ai'], item['behavior']), (ART, 'Streamer', True, 'still'))
        self.assertEqual(server.dispatch('GET', self.path + '/review', key=self.key)['pending'], [])

    def test_applying_before_creating_fails(self):
        with self.assertRaises(server.Error): self.bg('apply', {'use': 'preview'})

    def test_upload_replaces_the_previous_background(self):
        self.bg('apply', {'image': PNG})
        self.bg('apply', {'image': JPEG})
        item, = self.fulls()
        self.assertEqual((item['image'], item['ai']), (JPEG, False))

    def test_bad_uploads_are_rejected(self):
        bad = ['data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,' + base64.b64encode(b'not a png').decode(),
               'data:image/jpeg;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n').decode(), PNG[:-3] + '!!!', 'hello', 12,
               'data:image/png;base64,' + 'A' * 900_000]
        for image in bad:
            with self.assertRaises(server.Error, msg=str(image)[:40]): self.bg('apply', {'image': image})
        self.assertEqual(self.fulls(), [])

    def test_choosing_a_preset_or_clearing_removes_the_custom_background(self):
        self.bg('apply', {'image': PNG})
        server.dispatch('POST', self.path + '/theme', {'theme': 'sunset'}, self.key)
        self.assertEqual(self.fulls(), [])
        self.bg('apply', {'image': PNG}); self.bg('clear')
        self.assertEqual(self.fulls(), [])

    def test_clearing_keeps_objects(self):
        body = {'image': PNG, 'description': 'moon', 'creator': 'T', 'behavior': 'glow', 'x': 1, 'y': 2, 'polish': False}
        viewer = server.dispatch('POST', self.path + '/join')['viewer_token']
        with patch('server.moderate', return_value=False):
            server.dispatch('POST', self.path + '/submissions', body, viewer_token=viewer)
        server.dispatch('POST', self.path + '/approve/1', {}, self.key)
        self.bg('apply', {'image': PNG}); self.bg('clear')
        self.assertEqual([x['placement'] for x in self.state()['approved']], ['object'])

    def test_flagged_words_or_picture_are_never_applied(self):
        with patch('server.moderate_text', return_value=True), patch('server.generate_chat_art') as generate:
            with self.assertRaises(server.Error): self.bg('create', {'description': 'bad'})
        generate.assert_not_called()
        with patch('server.moderate_text', return_value=False), patch('server.moderate', return_value=True), patch('server.generate_chat_art', return_value=ART):
            with self.assertRaises(server.Error): self.bg('create', {'description': 'fine'})
        with self.assertRaises(server.Error): self.bg('apply', {'use': 'preview'})

    def test_creating_uses_the_rooms_art_limit(self):
        with patch.dict(os.environ, {'LITTLE_WORLDS_ART_LIMIT': '1'}):
            self.make_ai()
            with self.assertRaises(server.Error) as result: self.make_ai()
        self.assertEqual(result.exception.status, 429)

    def test_only_the_streamer_can_change_the_background(self):
        for name, body in (('create', {'description': 'x'}), ('apply', {'image': PNG}), ('clear', {})):
            with self.assertRaises(server.Error): self.bg(name, body, key='wrong')
        self.assertFalse(server.public_api_allowed('POST', self.path + '/background/clear'))

    def test_needs_ai_art_switched_on(self):
        with patch.dict(os.environ, {'LITTLE_WORLDS_AI_ART': ''}), patch('server.generate_chat_art') as generate:
            with self.assertRaises(server.Error): self.bg('create', {'description': 'x'})
        generate.assert_not_called()

if __name__ == '__main__': unittest.main()
