import base64
import os
import unittest
from unittest.mock import patch
import server

PNG = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nbody').decode()
WIDE = 'data:image/webp;base64,' + base64.b64encode(b'RIFFxxxxWEBPwide').decode()

class LibraryTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        room = server.dispatch('POST', '/api/rooms')
        self.path, self.key, self.code = '/api/rooms/' + room['code'], room['key'], room['code']
        self.viewer = server.dispatch('POST', self.path + '/join')['viewer_token']

    def streamer(self, route, body=None, method='POST'): return server.dispatch(method, self.path + route, body or {}, self.key)
    def review(self): return self.streamer('/review', method='GET')
    def scene(self): return server.dispatch('GET', self.path)['approved']

    def send(self, description='a moon'):
        body = {'image': PNG, 'description': description, 'creator': 'Mira', 'behavior': 'glow', 'x': 10, 'y': 20, 'polish': False}
        with patch('server.moderate', return_value=False):
            server.dispatch('POST', self.path + '/submissions', body, viewer_token=self.viewer)
        return max(x['id'] for x in self.review()['pending'])

    def approved(self, description='a moon'):
        item_id = self.send(description); self.streamer('/approve/%d' % item_id); return item_id

    def test_approving_saves_to_the_library_without_sending_pictures_in_the_poll(self):
        item_id = self.approved('a moon')
        entry, = self.review()['library']
        self.assertEqual((entry['id'], entry['description'], entry['creator'], entry['placement'], entry['ai']), (item_id, 'a moon', 'Mira', 'object', False))
        self.assertNotIn('image', entry)
        self.assertEqual(self.streamer('/library/%d' % item_id, method='GET'), {'image': PNG})

    def test_rejecting_does_not_save(self):
        self.streamer('/reject/%d' % self.send())
        self.assertEqual(self.review()['library'], [])

    def test_items_stay_in_the_library_after_leaving_the_scene(self):
        item_id = self.approved()
        self.streamer('/objects/%d' % item_id, method='DELETE'); self.streamer('/clear')
        self.assertEqual(self.scene(), [])
        self.assertEqual(len(self.review()['library']), 1)

    def test_use_as_full_background_replaces_the_old_one_and_leaves_the_library_alone(self):
        first = self.approved('first'); self.streamer('/library/%d/use' % first, {'as': 'full'})
        second = self.approved('second'); self.streamer('/library/%d/use' % second, {'as': 'full'})
        fulls = [x for x in self.scene() if x['placement'] == 'full']
        self.assertEqual(len(fulls), 1)
        self.assertEqual((fulls[0]['description'], fulls[0]['image'], fulls[0]['source'], fulls[0]['behavior']), ('second', PNG, 'library', 'still'))
        self.assertEqual(len(self.review()['library']), 2)
        self.assertEqual([x['id'] for x in self.scene() if x['placement'] == 'object'], [first, second])

    def test_use_as_piece_adds_a_larger_movable_background_piece(self):
        item_id = self.approved(); self.streamer('/library/%d/use' % item_id, {'as': 'piece'})
        piece, = [x for x in self.scene() if x['placement'] == 'backdrop']
        self.assertEqual((piece['scale'], piece['x'], piece['y'], piece['image']), (2.0, 50, 50, PNG))
        self.streamer('/library/%d/use' % item_id, {'as': 'piece'})
        self.assertEqual(len([x for x in self.scene() if x['placement'] == 'backdrop']), 2)

    def test_forgetting_removes_it_from_the_library_but_not_the_scene(self):
        item_id = self.approved()
        self.streamer('/library/%d/delete' % item_id)
        self.assertEqual(self.review()['library'], [])
        self.assertEqual(len(self.scene()), 1)

    def test_streamer_made_backgrounds_are_saved_too(self):
        self.streamer('/background/apply', {'image': PNG})
        entry, = self.review()['library']
        self.assertEqual((entry['creator'], entry['placement'], entry['description']), ('Streamer', 'full', 'Uploaded background'))

    def test_library_is_capped_to_the_newest_forty(self):
        with server.LOCK:
            room = server.ROOMS[self.code]
            for i in range(1, server.LIBRARY_LIMIT + 6): server.library_add(room, {'id': i, 'image': PNG, 'description': str(i)})
            server.library_add(room, {'id': 10, 'image': PNG, 'description': 'an id still in the library is not added twice'})
        ids = [x['id'] for x in self.review()['library']]
        self.assertEqual((len(ids), ids[0], ids[-1]), (server.LIBRARY_LIMIT, 6, server.LIBRARY_LIMIT + 5))

    def test_bad_requests(self):
        item_id = self.approved()
        for body in ({}, {'as': 'sky'}, {'as': 5}):
            with self.assertRaises(server.Error) as caught: self.streamer('/library/%d/use' % item_id, body)
            self.assertEqual(caught.exception.status, 400)
        with self.assertRaises(server.Error) as caught: self.streamer('/library/999/use', {'as': 'full'})
        self.assertEqual(caught.exception.status, 404)
        with self.assertRaises(server.Error) as caught: self.streamer('/library/999', method='GET')
        self.assertEqual(caught.exception.status, 404)

    def test_only_the_streamer_can_read_or_use_the_library(self):
        item_id = self.approved()
        for method, route, body in (('GET', '/library/%d' % item_id, {}), ('POST', '/library/%d/use' % item_id, {'as': 'full'}), ('POST', '/library/%d/delete' % item_id, {})):
            for key in ('', 'wrong'):
                with self.assertRaises(server.Error, msg=route): server.dispatch(method, self.path + route, body, key)
            with self.assertRaises(server.Error, msg=route): server.dispatch(method, self.path + route, body, viewer_token=self.viewer)
        for route in ('/library/1', '/library/1/use', '/library/1/delete'):
            self.assertFalse(server.public_api_allowed('GET', self.path + route)); self.assertFalse(server.public_api_allowed('POST', self.path + route))

    def test_viewers_never_see_the_library(self):
        self.approved()
        public = server.dispatch('GET', self.path)
        self.assertNotIn('library', public)

if __name__ == '__main__': unittest.main()
