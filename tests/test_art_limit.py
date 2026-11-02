import os
import unittest
from unittest.mock import patch
import server

class ArtLimitDisplayTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        room = server.dispatch('POST', '/api/rooms')
        self.path, self.key = '/api/rooms/' + room['code'], room['key']

    def reported_limit(self):
        return server.dispatch('GET', self.path + '/review', key=self.key)['chat_creation']['limit']

    def test_streamer_sees_the_default_limit_of_ten(self):
        with patch.dict(os.environ, {'LITTLE_WORLDS_ART_LIMIT': ''}):
            self.assertEqual(self.reported_limit(), 10)

    def test_streamer_sees_the_limit_that_is_actually_enforced(self):
        for value in ('3', '40'):
            with patch.dict(os.environ, {'LITTLE_WORLDS_ART_LIMIT': value}):
                self.assertEqual(self.reported_limit(), server.art_limit())
                self.assertEqual(self.reported_limit(), int(value))

    def test_nonsense_values_fall_back_to_ten(self):
        for value in ('lots', '0', '-4'):
            with patch.dict(os.environ, {'LITTLE_WORLDS_ART_LIMIT': value}):
                self.assertEqual(self.reported_limit(), server.art_limit())
                self.assertGreaterEqual(self.reported_limit(), 1)

if __name__ == '__main__': unittest.main()
