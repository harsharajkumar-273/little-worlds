import collections
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class HtmlIdsTest(unittest.TestCase):
    def test_ids_are_unique_in_every_page(self):
        # A duplicate id makes getElementById return the wrong element, e.g. a section instead of an input.
        for page in ('index.html', 'output.html'):
            ids = collections.Counter(re.findall(r'\sid="([^"]+)"', (ROOT / page).read_text()))
            self.assertEqual([k for k, v in ids.items() if v > 1], [], page)

    def test_every_id_used_by_the_scripts_exists(self):
        html = (ROOT / 'index.html').read_text()
        ids = set(re.findall(r'\sid="([^"]+)"', html))
        used = set(re.findall(r"\$\('([A-Za-z][A-Za-z0-9_]*)'\)", (ROOT / 'app.js').read_text()))
        self.assertEqual(sorted(used - ids), [])

if __name__ == '__main__': unittest.main()
