"""Frontend↔backend bridge contract.

The pywebview bridge is stringly-typed: the front-end calls `pyApiCall('name', ...)` (or
`window.pywebview.api.name(...)`) and pywebview dispatches to `AtlasApi.name`. A rename/removal on
either side leaves a silently dead button that no unit test sees. This test asserts every API name
the front-end calls actually exists on AtlasApi.
"""
import ast
import re
import unittest
from pathlib import Path

import atlas

ATLAS_DIR = Path(atlas.__file__).resolve().parent
MAIN_JS = ATLAS_DIR / 'view' / 'webview' / 'main.js'
API_PY = ATLAS_DIR / 'view' / 'webview' / 'api.py'


def _frontend_api_calls(js: str) -> set:
    names = set(re.findall(r"pyApiCall\(\s*['\"]([a-zA-Z_]\w*)['\"]", js))
    names |= set(re.findall(r"window\.pywebview\.api\.([a-zA-Z_]\w*)\s*\(", js))
    return names


def _atlas_api_methods(src: str) -> set:
    tree = ast.parse(src)
    methods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'AtlasApi':
            for n in node.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.add(n.name)
    return methods


class BridgeContractTest(unittest.TestCase):
    def test_every_frontend_api_call_resolves_to_an_atlasapi_method(self):
        calls = _frontend_api_calls(MAIN_JS.read_text())
        methods = _atlas_api_methods(API_PY.read_text())
        self.assertTrue(calls, "found no pyApiCall(...) names — parser/path likely broken")
        missing = sorted(c for c in calls if c not in methods)
        self.assertEqual(
            [], missing,
            f"front-end calls AtlasApi methods that don't exist (dead buttons): {missing}")


if __name__ == '__main__':
    unittest.main()
