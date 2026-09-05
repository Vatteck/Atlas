import json
import os
from unittest import TestCase

from atlas.gems.arch import naming

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), '..', '..',
                            'fixtures', 'pkg_name_normalization.json')


def load_fixture_cases():
    with open(os.path.abspath(FIXTURE_PATH)) as f:
        return json.load(f)['cases']


class NormalizePkgNameTest(TestCase):

    def test_shared_fixture_cases(self):
        cases = load_fixture_cases()
        self.assertTrue(cases, 'fixture must not be empty')

        for case in cases:
            with self.subTest(input=case['input']):
                self.assertEqual(case['expected'],
                                 naming.normalize_pkg_name(case['input']))

    def test_none_returns_empty_string(self):
        self.assertEqual('', naming.normalize_pkg_name(None))

    def test_build_suffix_is_not_stripped(self):
        # groupKey() in main.js strips build suffixes; this rule must not, or a search
        # for 'brave-bin' would stop finding brave-bin.
        self.assertEqual('bravebin', naming.normalize_pkg_name('brave-bin'))
        self.assertNotEqual(naming.normalize_pkg_name('brave'),
                            naming.normalize_pkg_name('brave-bin'))
