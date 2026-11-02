import base64
import os
import unittest
from unittest.mock import patch
import server

IMAGE = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode()
ART = 'data:image/webp;base64,' + base64.b64encode(b'RIFFxxxxWEBPart').decode()

class CreateModeTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        room = server.dispatch('POST', '/api/rooms')
        self.path, self.key = '/api/rooms/' + room['code'], room['key']
        self.viewer = server.dispatch('POST', self.path + '/join')['viewer_token']
        env = patch.dict(os.environ, {'LITTLE_WORLDS_AI_ART': '1', 'OPENAI_API_KEY': 'test', 'LITTLE_WORLDS_ART_LIMIT': '50'})
        env.start(); self.addCleanup(env.stop)
        self.words = {'description': 'A smiling cloud', 'creator': 'Tester', 'mode': 'create', 'style': 'cartoon'}
        self.send_body = self.words | {'behavior': 'float', 'x': 40, 'y': 50, 'polish': True}

    def call(self, name, body):
        return server.dispatch('POST', self.path + '/' + name, body, viewer_token=self.viewer)

    def queue(self):
        return server.dispatch('GET', self.path + '/review', key=self.key)['pending']

    def test_create_needs_no_drawing_and_passes_the_style_through(self):
        with patch('server.moderate_text', return_value=False), patch('server.moderate', return_value=False), \
                patch('server.generate_chat_art', return_value=ART) as generate:
            result = self.call('preview', self.words)
        generate.assert_called_once_with('A smiling cloud', 'cartoon')
        self.assertEqual(result['art'], ART)
        self.assertEqual(self.queue(), [])

    def test_sending_a_created_preview_queues_it_with_no_original(self):
        with patch('server.moderate_text', return_value=False), patch('server.moderate', return_value=False), \
                patch('server.generate_chat_art', return_value=ART) as generate:
            self.call('preview', self.words)
            self.call('submissions', self.send_body)
        generate.assert_called_once()
        item = self.queue()[0]
        self.assertEqual((item['image'], item['ai'], item['scale']), (ART, True, 1.0))
        self.assertNotIn('original', item)

    def test_cannot_send_create_mode_without_a_matching_preview(self):
        with patch('server.moderate', return_value=False):
            with self.assertRaises(server.Error): self.call('submissions', self.send_body)
        self.assertEqual(self.queue(), [])

    def test_changed_words_or_style_invalidate_the_preview(self):
        with patch('server.moderate_text', return_value=False), patch('server.moderate', return_value=False), \
                patch('server.generate_chat_art', return_value=ART):
            self.call('preview', self.words)
            for change in ({'description': 'A grumpy cloud'}, {'style': 'pixel'}):
                with self.assertRaises(server.Error): self.call('submissions', self.send_body | change)

    def test_flagged_words_never_generate_and_warn(self):
        with patch('server.moderate_text', return_value=True), patch('server.generate_chat_art') as generate:
            with self.assertRaises(server.Error) as result: self.call('preview', self.words)
        generate.assert_not_called()
        self.assertEqual(result.exception.details['warnings'], 1)

    def test_unknown_style_is_rejected(self):
        with self.assertRaises(server.Error): self.call('preview', self.words | {'style': 'evil'})

    def test_polish_style_reaches_the_generator(self):
        body = {'image': IMAGE, 'description': 'A moon', 'creator': 'Tester', 'style': 'pixel'}
        with patch('server.moderate', return_value=False), patch('server.generate_art', return_value=ART) as generate:
            self.call('preview', body)
        generate.assert_called_once_with(IMAGE, 'A moon', 'pixel')

class ScaleTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        room = server.dispatch('POST', '/api/rooms')
        self.path, self.key = '/api/rooms/' + room['code'], room['key']
        self.viewer = server.dispatch('POST', self.path + '/join')['viewer_token']
        body = {'image': IMAGE, 'description': 'A moon', 'creator': 'T', 'behavior': 'glow', 'x': 10, 'y': 20}
        with patch('server.moderate', return_value=False):
            server.dispatch('POST', self.path + '/submissions', body, viewer_token=self.viewer)

    def post(self, route, body): return server.dispatch('POST', self.path + route, body, self.key)

    def test_resize_a_waiting_creation_then_approve_keeps_the_size(self):
        self.post('/placement/1', {'scale': 1.8})
        self.post('/approve/1', {})
        self.assertEqual(server.dispatch('GET', self.path)['approved'][0]['scale'], 1.8)

    def test_resize_an_approved_object_without_moving_it(self):
        self.post('/approve/1', {})
        self.post('/objects/1', {'scale': 0.5})
        item = server.dispatch('GET', self.path)['approved'][0]
        self.assertEqual((item['scale'], item['x'], item['y']), (0.5, 10, 20))

    def test_moving_does_not_reset_the_size(self):
        self.post('/approve/1', {})
        self.post('/objects/1', {'scale': 2})
        self.post('/objects/1', {'x': 60, 'y': 70})
        item = server.dispatch('GET', self.path)['approved'][0]
        self.assertEqual((item['scale'], item['x']), (2, 60))

    def test_bad_sizes_are_rejected(self):
        self.post('/approve/1', {})
        for bad in (0, 0.1, 4.5, -1, True, 'big', float('nan')):
            with self.assertRaises(server.Error): self.post('/objects/1', {'scale': bad})

    def test_only_the_streamer_can_resize(self):
        self.post('/approve/1', {})
        with self.assertRaises(server.Error): server.dispatch('POST', self.path + '/objects/1', {'scale': 2}, 'wrong')

if __name__ == '__main__': unittest.main()
