#!/usr/bin/env python3
"""Live check of moderation + AI art against the real OpenAI API (costs a few cents).
Run from the project folder with OPENAI_API_KEY set:  python3 scripts/live_ai_art_check.py
Writes the generated picture to live_art_result.webp so you can look at it."""
import base64, os, struct, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

def sample_drawing():
    """A 600x400 transparent PNG with a white crescent-ish circle, made with the standard library only."""
    w, h, rows = 600, 400, []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            d = (x - 300) ** 2 + (y - 200) ** 2
            inside = d < 90 ** 2 and (x - 340) ** 2 + (y - 180) ** 2 > 75 ** 2
            row += bytes((248, 244, 255, 255)) if inside else bytes((0, 0, 0, 0))
        rows.append(bytes(row))
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b'')
    return 'data:image/png;base64,' + base64.b64encode(png).decode()

if not os.environ.get('OPENAI_API_KEY', '').strip(): sys.exit('Set OPENAI_API_KEY first (see README).')
image, description = sample_drawing(), 'A glowing crescent moon over the city'
print('1/3 moderating the drawing…')
print('    flagged:', server.moderate(image, description, 'tester'))
print('2/3 generating AI art (can take up to a minute)…')
art = server.generate_art(image, description)
if not art: sys.exit('    FAILED: no art returned (model access, billing or request format). See the AI art generation failed line above.')
print('    ok,', len(art) // 1024, 'KB')
print('3/3 moderating the generated art…')
print('    flagged:', server.moderate(art, description, 'tester'))
open('live_art_result.webp', 'wb').write(base64.b64decode(art.partition(',')[2]))
print('Saved live_art_result.webp')
