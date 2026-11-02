import base64
import json
import threading
import unittest
import urllib.request
from unittest.mock import patch
import server

class OutputHttpTest(unittest.TestCase):
    def test_output_page_and_approved_only_endpoint(self):
        server.ROOMS.clear()
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{httpd.server_port}'
        def request(path, body=None, key=None, viewer=None):
            headers = {'Content-Type': 'application/json'}
            if key: headers['X-Streamer-Key'] = key
            if viewer: headers['X-Viewer-Token'] = viewer
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
            with urllib.request.urlopen(req, timeout=3) as response: return json.load(response)
        try:
            with urllib.request.urlopen(base + '/output?room=ABC234', timeout=3) as page:
                self.assertIn(b'/output.js', page.read())
            created = request('/api/rooms', {})
            path = '/api/rooms/' + created['code']
            viewer = request(path + '/join', {})['viewer_token']
            image = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode()
            with patch('server.moderate', return_value=False):
                request(path + '/submissions', {'image': image, 'description': 'moon', 'creator': 'viewer123', 'behavior': 'glow', 'x': 30, 'y': 40}, viewer=viewer)
            self.assertEqual(request(path)['approved'], [])
            request(path + '/approve/1', {}, key=created['key'])
            self.assertEqual(request(path)['approved'][0]['behavior'], 'glow')
            request(path + '/clear', {}, key=created['key'])
            self.assertEqual(request(path)['approved'], [])
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()

if __name__ == '__main__': unittest.main()
