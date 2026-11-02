import base64
import concurrent.futures
import unittest
from unittest.mock import patch
import server

IMAGE = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode()

class ModerationFlowTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        room = server.dispatch('POST', '/api/rooms')
        self.path, self.key = '/api/rooms/' + room['code'], room['key']
        self.viewer = server.dispatch('POST', self.path + '/join')['viewer_token']
        self.body = {'image': IMAGE, 'description': 'A moon', 'creator': 'viewer123', 'behavior': 'glow', 'x': 10, 'y': 20}

    def send(self):
        return server.dispatch('POST', self.path + '/submissions', self.body, viewer_token=self.viewer)

    def test_pass_is_private_until_approved(self):
        with patch('server.moderate', return_value=False) as moderation:
            self.send()
        moderation.assert_called_once_with(IMAGE, 'A moon', 'viewer123')
        self.assertEqual(server.dispatch('GET', self.path)['approved'], [])
        with self.assertRaises(server.Error): server.dispatch('GET', self.path + '/review')
        queue = server.dispatch('GET', self.path + '/review', key=self.key)['pending']
        self.assertEqual(queue[0]['description'], 'A moon')
        self.assertEqual(queue[0]['creator'], 'viewer123')
        server.dispatch('POST', self.path + '/approve/1', key=self.key)
        self.assertEqual(server.dispatch('GET', self.path)['approved'][0]['creator'], 'viewer123')

    def test_output_state_excludes_rejected_and_tracks_changes(self):
        with patch('server.moderate', return_value=False):
            self.send()
            self.send()
        self.assertEqual(server.dispatch('GET', self.path)['approved'], [])
        server.dispatch('POST', self.path + '/reject/1', key=self.key)
        server.dispatch('POST', self.path + '/approve/2', key=self.key)
        self.assertEqual([x['id'] for x in server.dispatch('GET', self.path)['approved']], [2])
        server.dispatch('POST', self.path + '/objects/2', {'x': 60, 'y': 70}, self.key)
        self.assertEqual(server.dispatch('GET', self.path)['approved'][0]['x'], 60)
        server.dispatch('POST', self.path + '/clear', key=self.key)
        self.assertEqual(server.dispatch('GET', self.path)['approved'], [])

    def test_invalid_names_never_reach_moderation(self):
        with patch('server.moderate') as moderation:
            for name in ('', 'x' * 26, 'bad\nname'):
                self.body['creator'] = name
                with self.assertRaises(server.Error): self.send()
            moderation.assert_not_called()

    def test_theme_change_requires_streamer_and_preserves_scene(self):
        with patch('server.moderate', return_value=False):
            self.send(); self.send()
        server.dispatch('POST', self.path + '/approve/1', key=self.key)
        before = server.dispatch('GET', self.path)['approved']
        with self.assertRaises(server.Error):
            server.dispatch('POST', self.path + '/theme', {'theme':'space'})
        with self.assertRaises(server.Error):
            server.dispatch('POST', self.path + '/theme', {'theme':'invalid'}, self.key)
        server.dispatch('POST', self.path + '/theme', {'theme':'space'}, self.key)
        public = server.dispatch('GET', self.path)
        review = server.dispatch('GET', self.path + '/review', key=self.key)
        self.assertEqual((public['theme'], review['theme']), ('space', 'space'))
        self.assertEqual(public['approved'], before)
        self.assertNotIn('pending', public)
        self.assertEqual(len(review['pending']), 1)
        server.dispatch('POST', self.path + '/theme', {'theme':'neon'}, self.key)
        self.assertEqual(server.dispatch('GET', self.path)['theme'], 'neon')

    def test_three_flags_block_and_do_not_reach_queue(self):
        with patch('server.moderate', return_value=True) as moderation:
            for count in range(1, 4):
                with self.assertRaises(server.Error) as result: self.send()
                self.assertEqual(result.exception.details['warnings'], count)
            with self.assertRaises(server.Error): self.send()
            self.assertEqual(moderation.call_count, 3)
        self.assertEqual(server.dispatch('GET', self.path + '/review', key=self.key)['pending'], [])
        joined = server.dispatch('POST', self.path + '/join', viewer_token=self.viewer)
        self.assertEqual(joined['warnings'], 3)

    def test_unavailable_does_not_warn_or_queue(self):
        with patch('server.moderate', side_effect=server.Error(503, 'unavailable')):
            with self.assertRaises(server.Error) as result: self.send()
            self.assertEqual(result.exception.status, 503)
        self.assertEqual(server.dispatch('GET', self.path + '/viewer', viewer_token=self.viewer)['warnings'], 0)
        self.assertEqual(server.dispatch('GET', self.path + '/review', key=self.key)['pending'], [])

    def test_concurrent_requests_cannot_bypass_limit(self):
        def attempt(_):
            try: self.send()
            except server.Error: pass
        with patch('server.moderate', return_value=True) as moderation:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(attempt, range(8)))
            self.assertEqual(moderation.call_count, 3)
        self.assertEqual(server.dispatch('GET', self.path + '/viewer', viewer_token=self.viewer)['warnings'], 3)

    def test_paused_and_invalid_never_call_provider(self):
        server.dispatch('POST', self.path + '/pause', {'paused': True}, self.key)
        with patch('server.moderate') as moderation:
            with self.assertRaises(server.Error): self.send()
            server.dispatch('POST', self.path + '/pause', {'paused': False}, self.key)
            self.body['description'] = '   '
            with self.assertRaises(server.Error): self.send()
            moderation.assert_not_called()

    def test_missing_key_fails_closed(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(server.Error) as result: self.send()
        self.assertEqual(result.exception.status, 503)
        self.assertEqual(server.dispatch('GET', self.path + '/viewer', viewer_token=self.viewer)['warnings'], 0)

if __name__ == '__main__': unittest.main()
