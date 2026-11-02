import os
import unittest
from unittest.mock import patch
import server

ART = 'data:image/webp;base64,UklGRg=='

class PlacementTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        room = server.dispatch('POST', '/api/rooms')
        self.path, self.key = '/api/rooms/' + room['code'], room['key']
        self.viewer = server.dispatch('POST', self.path + '/join')['viewer_token']
        env = patch.dict(os.environ, {'LITTLE_WORLDS_AI_ART': '1', 'OPENAI_API_KEY': 'test', 'LITTLE_WORLDS_ART_LIMIT': '50'})
        env.start(); self.addCleanup(env.stop)
        self.words = {'description': 'A sunny hillside', 'creator': 'Tester', 'mode': 'create', 'style': 'watercolor'}

    def call(self, name, body): return server.dispatch('POST', self.path + '/' + name, body, viewer_token=self.viewer)
    def streamer(self, route): return server.dispatch('POST', self.path + route, {}, self.key)
    def pending(self): return server.dispatch('GET', self.path + '/review', key=self.key)['pending']

    def make(self, kind):
        body = self.words | {'placement': kind}
        with patch('server.moderate_text', return_value=False), patch('server.moderate', return_value=False), \
                patch('server.generate_chat_art', return_value=ART) as generate:
            self.call('preview', body)
            self.call('submissions', body | {'behavior': 'rain', 'x': 10, 'y': 20})
        return generate

    def test_default_is_an_object(self):
        self.make('object')
        item = self.pending()[0]
        self.assertEqual((item['placement'], item['scale'], item['behavior'], item['x']), ('object', 1.0, 'rain', 10))

    def test_scenery_piece_starts_larger_and_keeps_its_spot(self):
        self.make('backdrop').assert_called_once_with('A sunny hillside', 'watercolor', kind='backdrop')
        item = self.pending()[0]
        self.assertEqual((item['placement'], item['scale'], item['x'], item['y']), ('backdrop', 2.0, 10, 20))

    def test_full_background_is_centered_still_and_asks_for_a_wide_image(self):
        self.make('full').assert_called_once_with('A sunny hillside', 'watercolor', kind='full')
        item = self.pending()[0]
        self.assertEqual((item['placement'], item['behavior'], item['x'], item['y']), ('full', 'still', 50, 50))

    def test_new_full_background_replaces_the_old_one_but_keeps_everything_else(self):
        for kind in ('full', 'backdrop', 'full'): self.make(kind)
        for item in self.pending(): self.streamer('/approve/%d' % item['id'])
        approved = server.dispatch('GET', self.path)['approved']
        self.assertEqual(sorted(x['placement'] for x in approved), ['backdrop', 'full'])
        self.assertEqual([x['id'] for x in approved if x['placement'] == 'full'], [3])

    def test_preview_for_one_placement_cannot_be_sent_as_another(self):
        body = self.words | {'placement': 'object'}
        with patch('server.moderate_text', return_value=False), patch('server.moderate', return_value=False), \
                patch('server.generate_chat_art', return_value=ART):
            self.call('preview', body)
            with self.assertRaises(server.Error):
                self.call('submissions', body | {'placement': 'full', 'behavior': 'still', 'x': 1, 'y': 1})

    def test_unknown_placement_is_rejected(self):
        with self.assertRaises(server.Error): self.call('preview', self.words | {'placement': 'sky'})

    def test_art_options_by_kind(self):
        self.assertEqual(server.art_options('full'), ('1536x1024', 'opaque'))
        self.assertEqual(server.art_options('object'), ('1024x1024', 'transparent'))
        self.assertEqual(server.art_options('backdrop'), ('1024x1024', 'transparent'))

if __name__ == '__main__': unittest.main()
