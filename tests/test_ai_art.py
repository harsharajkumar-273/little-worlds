import base64
import os
import unittest
from unittest.mock import patch
import server

IMAGE = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode()
ART = 'data:image/webp;base64,' + base64.b64encode(b'RIFFartwork').decode()

class AiArtTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        room = server.dispatch('POST', '/api/rooms')
        self.path, self.key = '/api/rooms/' + room['code'], room['key']
        self.viewer = server.dispatch('POST', self.path + '/join')['viewer_token']
        self.body = {'image': IMAGE, 'description': 'A moon', 'creator': 'viewer123', 'behavior': 'glow', 'x': 10, 'y': 20}
        env = patch.dict(os.environ, {'LITTLE_WORLDS_AI_ART': '1', 'OPENAI_API_KEY': 'test'})
        env.start(); self.addCleanup(env.stop)

    def send(self):
        return server.dispatch('POST', self.path + '/submissions', self.body, viewer_token=self.viewer)

    def queue(self):
        return server.dispatch('GET', self.path + '/review', key=self.key)['pending'][0]

    def test_art_replaces_drawing_and_original_stays_private(self):
        with patch('server.moderate', return_value=False) as moderation, patch('server.generate_art', return_value=ART):
            self.send()
        self.assertEqual(moderation.call_count, 2)
        item = self.queue()
        self.assertEqual((item['image'], item['original'], item['ai']), (ART, IMAGE, True))
        server.dispatch('POST', self.path + '/approve/1', key=self.key)
        public = server.dispatch('GET', self.path)['approved'][0]
        self.assertEqual(public['image'], ART)
        self.assertNotIn('original', public)

    def test_flagged_art_falls_back_to_drawing(self):
        with patch('server.moderate', side_effect=[False, True]), patch('server.generate_art', return_value=ART):
            self.send()
        item = self.queue()
        self.assertEqual((item['image'], item['ai']), (IMAGE, False))

    def test_generation_failure_falls_back_to_drawing(self):
        with patch('server.moderate', return_value=False), patch('server.generate_art', return_value=None):
            self.send()
        self.assertFalse(self.queue()['ai'])

    def test_disabled_without_flag_never_calls_generator(self):
        with patch.dict(os.environ, {'LITTLE_WORLDS_AI_ART': ''}), patch('server.moderate', return_value=False), \
                patch('server.generate_art') as generate:
            self.send()
        generate.assert_not_called()
        self.assertFalse(self.queue()['ai'])

    def test_shared_generation_cap_preserves_original(self):
        room=server.ROOMS[self.path.rsplit('/',1)[-1]]
        room['chat_attempts']=10
        with patch('server.moderate',return_value=False), patch('server.generate_art') as generate:
            self.send()
        generate.assert_not_called()
        self.assertEqual(self.queue()['image'],IMAGE)

    def test_viewer_can_opt_out_of_polish(self):
        self.body['polish'] = False
        with patch('server.moderate', return_value=False), patch('server.generate_art') as generate:
            self.send()
        generate.assert_not_called()
        self.assertFalse(self.queue()['ai'])

    def test_flagged_drawing_never_reaches_generator(self):
        with patch('server.moderate', return_value=True), patch('server.generate_art') as generate:
            with self.assertRaises(server.Error): self.send()
        generate.assert_not_called()

    def preview(self):
        body = {k: self.body[k] for k in ('image', 'description')} | {'creator': 'Tester'}
        return server.dispatch('POST', self.path + '/preview', body, viewer_token=self.viewer)

    def test_preview_is_private_and_sending_reuses_it_without_generating_again(self):
        self.body['creator'] = 'Tester'
        with patch('server.moderate', return_value=False), patch('server.generate_art', return_value=ART) as generate:
            result = self.preview()
            self.assertEqual(result, {'art': ART, 'previews_left': server.PREVIEW_LIMIT - 1})
            self.assertEqual(server.dispatch('GET', self.path + '/review', key=self.key)['pending'], [])
            self.send()
        generate.assert_called_once()
        item = self.queue()
        self.assertEqual((item['image'], item['original'], item['ai']), (ART, IMAGE, True))

    def test_changed_description_after_preview_generates_again(self):
        self.body['creator'] = 'Tester'
        with patch('server.moderate', return_value=False), patch('server.generate_art', return_value=ART) as generate:
            self.preview()
            self.body['description'] = 'A different moon'
            self.send()
        self.assertEqual(generate.call_count, 2)

    def test_viewer_preview_limit(self):
        with patch('server.moderate', return_value=False), patch('server.generate_art', return_value=ART), \
                patch.dict(os.environ, {'LITTLE_WORLDS_ART_LIMIT': '50'}):
            for _ in range(server.PREVIEW_LIMIT): self.preview()
            with self.assertRaises(server.Error) as result: self.preview()
        self.assertEqual(result.exception.status, 429)

    def test_room_art_limit_applies_to_previews(self):
        with patch('server.moderate', return_value=False), patch('server.generate_art', return_value=ART), \
                patch.dict(os.environ, {'LITTLE_WORLDS_ART_LIMIT': '2'}):
            self.preview(); self.preview()
            with self.assertRaises(server.Error) as result: self.preview()
        self.assertEqual(result.exception.status, 429)

    def test_flagged_preview_art_is_never_returned_and_warns(self):
        with patch('server.moderate', side_effect=[False, True]), patch('server.generate_art', return_value=ART):
            with self.assertRaises(server.Error) as result: self.preview()
        self.assertEqual(result.exception.details['warnings'], 1)

    def test_preview_requires_ai_art_on(self):
        with patch.dict(os.environ, {'LITTLE_WORLDS_AI_ART': ''}), patch('server.generate_art') as generate:
            with self.assertRaises(server.Error): self.preview()
        generate.assert_not_called()

    def test_preview_is_allowed_on_public_endpoint(self):
        self.assertTrue(server.public_api_allowed('POST', self.path + '/preview'))

if __name__ == '__main__': unittest.main()
