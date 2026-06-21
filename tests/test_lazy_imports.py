"""Launch-perf regression guard (see docs/plans/2026-06-20-launch-optimization.md).

The HTTP/parse stack (requests/urllib3/charset_normalizer/chardet/bs4/lxml) is ~0.5 s of import time
and is deliberately NOT loaded at startup — it's imported lazily on first network call / page parse.
A stray top-level `import requests` in any startup-path module would silently undo that. This runs a
fresh subprocess that imports everything launch loads (app head + every gem controller, the way
load_managers does) and asserts none of the heavy stack came in.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

import atlas

REPO_ROOT = Path(atlas.__file__).resolve().parent.parent

_PROBE = r"""
import importlib, os, sys
import atlas.app                      # app.py module-level imports
from atlas.api.http import HttpClient # context/http path
from atlas import ROOT_DIR
# import every gem controller exactly as load_managers() does
for d in os.scandir(os.path.join(ROOT_DIR, 'gems')):
    if d.is_dir() and d.name != '__pycache__':
        try:
            importlib.import_module('atlas.gems.%s.controller' % d.name)
        except Exception:
            pass
heavy = ('requests', 'urllib3', 'charset_normalizer', 'chardet', 'bs4', 'lxml')
loaded = [m for m in heavy if m in sys.modules]
print('LOADED:' + ','.join(loaded))
"""


class LazyImportGuardTest(unittest.TestCase):
    def test_heavy_http_parse_stack_not_imported_at_startup(self):
        env = dict(os.environ)
        # Ensure the subprocess imports this working tree, not an installed snapshot.
        env['PYTHONPATH'] = os.pathsep.join([str(REPO_ROOT)] + sys.path)
        out = subprocess.run([sys.executable, '-c', _PROBE],
                             capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(0, out.returncode, f"probe failed:\n{out.stderr}")
        line = next((l for l in out.stdout.splitlines() if l.startswith('LOADED:')), None)
        self.assertIsNotNone(line, f"probe produced no result:\n{out.stdout}\n{out.stderr}")
        loaded = [m for m in line[len('LOADED:'):].split(',') if m]
        self.assertEqual(
            [], loaded,
            f"heavy import stack pulled onto the launch path (regression): {loaded}. "
            f"Move the offending top-level `import` into the function that uses it.")


if __name__ == '__main__':
    unittest.main()
