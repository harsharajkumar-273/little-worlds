#!/usr/bin/env python3
"""Smoke test for the webcam cut-out in real Chrome, using Chrome's built-in fake camera. No keys or network needed.
It starts a throwaway server on a random port, drives the streamer page over the DevTools protocol, and checks that
the model loads, frames are processed, and the canvas gets transparent pixels. It cannot judge quality on a real person.
Run:  .venv/bin/python scripts/cutout_smoke.py"""
import json, os, subprocess, sys, tempfile, threading, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server
from websockets.sync.client import connect

CHROME = os.environ.get('CHROME', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{httpd.server_port}/'
profile = tempfile.mkdtemp()
chrome = subprocess.Popen([CHROME, '--headless=new', '--remote-debugging-port=9333', '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream', '--no-first-run', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', f'--user-data-dir={profile}', 'about:blank'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
messages, counter = [], [0]
try:
    for _ in range(50):
        try: target = next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type'] == 'page'); break
        except Exception: time.sleep(0.2)
    ws = connect(target['webSocketDebuggerUrl'], max_size=None)
    def send(method, **params):
        counter[0] += 1; want = counter[0]
        ws.send(json.dumps({'id': want, 'method': method, 'params': params}))
        while True:
            reply = json.loads(ws.recv(timeout=60))
            if reply.get('method') == 'Runtime.exceptionThrown': messages.append('EXCEPTION ' + json.dumps(reply['params']['exceptionDetails'].get('exception', {}).get('description', ''))[:300])
            if reply.get('method') == 'Runtime.consoleAPICalled' and reply['params']['type'] in ('error', 'warning'):
                messages.append(reply['params']['type'] + ' ' + ' '.join(str(a.get('value', a.get('description', ''))) for a in reply['params']['args'])[:300])
            if reply.get('id') == want: return reply.get('result', {})
    def js(expression):
        result = send('Runtime.evaluate', expression=expression, awaitPromise=True, returnByValue=True)
        return result.get('result', {}).get('value')
    send('Runtime.enable'); send('Page.enable')
    send('Page.navigate', url=base); time.sleep(1.5)
    js("document.getElementById('createRoom').click(); new Promise(r => setTimeout(r, 800))")
    js("document.getElementById('webcamToggle').click(); 1")
    stats = None
    for _ in range(60):
        time.sleep(1)
        stats = js("""(() => { const c = document.getElementById('webcamCanvas'), box = document.getElementById('webcamBox');
          if (!box.classList.contains('cut') || !c.width) return {ready: false, status: document.getElementById('webcamStatus').textContent};
          const d = c.getContext('2d', {willReadFrequently: true}).getImageData(0, 0, c.width, c.height).data; let clear = 0, solid = 0, soft = 0;
          for (let i = 3; i < d.length; i += 4) { if (d[i] === 0) clear++; else if (d[i] === 255) solid++; else soft++; }
          return {ready: true, w: c.width, h: c.height, clear, solid, soft, status: document.getElementById('webcamStatus').textContent}; })()""")
        if stats and stats.get('ready') and (stats['clear'] + stats['solid'] + stats['soft']) > 0 and (stats['clear'] or stats['soft']): break
    print(json.dumps(stats, indent=1))
    ok = bool(stats and stats.get('ready')) and (stats['clear'] + stats['soft'] > 0)
    # Turning it off must stop the camera and hide the canvas.
    js("document.getElementById('webcamToggle').click(); 1"); time.sleep(0.5)
    print('after off ->', js("({canvasHidden: document.getElementById('webcamCanvas').hidden, live: document.getElementById('webcamBox').classList.contains('live')})"))
    print('console problems:', messages or 'none')
    print('PASS: model loaded and the camera frame was cut out.' if ok else 'FAIL: no cut-out frames were produced.')
    sys.exit(0 if ok else 1)
finally:
    chrome.terminate(); httpd.shutdown()
