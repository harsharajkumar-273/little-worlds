import hashlib
import threading
import unittest
import urllib.request
from pathlib import Path
import server

ROOT = Path(__file__).resolve().parent.parent
SHA256 = {
    'vendor/mediapipe/vision_bundle.mjs': '870da5cfc43bfcf2a8b0f14e8152dae8c7e701722e1191b0e592b94b81b4127a',
    'vendor/mediapipe/wasm/vision_wasm_internal.js': '85c1a342be70427987f900969a5f26e17557351111364e6585e97fb03e93e108',
    'vendor/mediapipe/wasm/vision_wasm_internal.wasm': 'bcc13df22d3d69ec8cbe8e280989356d844ae00f4523eb82072d2484f44134dc',
    'vendor/mediapipe/selfie_segmenter.tflite': '191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b',
}

class VendorFilesTest(unittest.TestCase):
    def test_vendored_files_match_the_recorded_checksums(self):
        for name, expected in SHA256.items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected, name)

    def test_server_serves_them_with_the_right_types(self):
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{httpd.server_port}'
        try:
            for path, kind in (('/cutout.js', 'text/javascript'), ('/promptkit.js', 'text/javascript'), ('/vendor/mediapipe/vision_bundle.mjs', 'text/javascript'),
                               ('/vendor/mediapipe/wasm/vision_wasm_internal.wasm', 'application/wasm'),
                               ('/vendor/mediapipe/selfie_segmenter.tflite', 'application/octet-stream')):
                with urllib.request.urlopen(base + path, timeout=5) as response:
                    self.assertEqual(response.status, 200, path)
                    self.assertTrue(response.headers['Content-Type'].startswith(kind), path)
            for bad in ('/vendor/', '/vendor/mediapipe/NOTICE.md', '/vendor/../server.py', '/vendor/mediapipe/../../server.py'):
                with self.assertRaises(urllib.error.HTTPError, msg=bad) as caught: urllib.request.urlopen(base + bad, timeout=5)
                self.assertEqual(caught.exception.code, 404, bad)
        finally:
            httpd.shutdown()

if __name__ == '__main__': unittest.main()
