import base64
from collections import deque
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import server

ORIGIN='https://demo.trycloudflare.com'
IMAGE='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode()
class ViewerBoundaryTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.http.viewer_only=True;self.http.viewer_origin=ORIGIN;self.http.public_events=deque()
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.http.server_port}'
        created=server.dispatch('POST','/api/rooms');self.path='/api/rooms/'+created['code'];self.key=created['key']
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join()
    def req(self,path,method='GET',body=None,host='demo.trycloudflare.com',origin=None,extra=None):
        headers={'Host':host,**(extra or {})}
        if origin is not None:headers['Origin']=origin
        if body is not None:headers['Content-Type']='application/json'
        r=urllib.request.Request(self.base+path,method=method,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(r,timeout=3) as response:return response.status,response.read()
        except urllib.error.HTTPError as e:
            try: return e.code,e.read()
            finally: e.close()
    def test_boundary_denies_privileged_routes_even_with_keys_and_spoofed_headers(self):
        for method,path in [('GET',self.path+'/review'),('POST',self.path+'/approve/1'),('POST',self.path+'/theme'),('POST',self.path+'/clear'),('POST',self.path+'/twitch/share'),('POST','/api/rooms'),('GET','/twitch/callback'),('GET','/output')]:
            status,_=self.req(path,method,{} if method=='POST' else None,origin=ORIGIN,extra={'X-Streamer-Key':self.key,'X-Forwarded-Host':'localhost:8765','X-Forwarded-Proto':'http'})
            self.assertEqual(status,403,(method,path))
        self.assertEqual(self.req(self.path+'/review',host=f'localhost:{self.http.server_port}',extra={'X-Streamer-Key':self.key})[0],403)
        self.assertEqual(self.req(self.path+'/join','POST',{},origin='https://evil.example')[0],403)
        self.assertEqual(self.req(self.path+'/join','POST',{})[0],403)
    def test_viewer_join_submission_and_privacy(self):
        status,page=self.req('/');self.assertEqual(status,200);self.assertIn(b'data-viewer-only="true"',page)
        status,data=self.req(self.path+'/join','POST',{},origin=ORIGIN);self.assertEqual(status,200);token=json.loads(data)['viewer_token']
        body={'image':IMAGE,'description':'moon','creator':'artist','behavior':'still','x':20,'y':30}
        with patch('server.moderate',return_value=False),patch('server.ai_art_enabled',return_value=False):
            status,_=self.req(self.path+'/submissions','POST',body,origin=ORIGIN,extra={'X-Viewer-Token':token})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(self.req(self.path)[1])['approved'],[])
        self.assertEqual(self.req(self.path+'/review')[0],403)
        self.assertEqual(len(server.dispatch('GET',self.path+'/review',key=self.key)['pending']),1)
    def test_join_limit(self):
        for _ in range(20):self.assertEqual(self.req(self.path+'/join','POST',{},origin=ORIGIN)[0],200)
        self.assertEqual(self.req(self.path+'/join','POST',{},origin=ORIGIN)[0],429)
    def test_submission_limit(self):
        token=json.loads(self.req(self.path+'/join','POST',{},origin=ORIGIN)[1])['viewer_token']
        body={'image':IMAGE,'description':'moon','creator':'artist','behavior':'still','x':20,'y':30}
        with patch('server.moderate',return_value=False),patch('server.ai_art_enabled',return_value=False):
            for _ in range(10):self.assertEqual(self.req(self.path+'/submissions','POST',body,origin=ORIGIN,extra={'X-Viewer-Token':token})[0],200)
            self.assertEqual(self.req(self.path+'/submissions','POST',body,origin=ORIGIN,extra={'X-Viewer-Token':token})[0],429)
    def test_origin_configuration_validation(self):
        for value in ['http://demo.trycloudflare.com','https://evil.example','https://demo.trycloudflare.com:8766','https://demo.trycloudflare.com/path']:
            with patch.dict('os.environ',{'PUBLIC_VIEWER_ORIGIN':value}):
                with self.assertRaises(ValueError):server.viewer_origin()
        with patch.dict('os.environ',{'PUBLIC_VIEWER_ORIGIN':ORIGIN}):self.assertEqual(server.viewer_origin(),ORIGIN)

if __name__=='__main__':unittest.main()
