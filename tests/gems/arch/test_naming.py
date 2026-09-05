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


class MatchIndexNamesTest(TestCase):

    # Keys as read_local_index() returns them: worker.py strips [-_.] when writing.
    INDEX = {
        'googlechrome': 'google-chrome',
        'googlechromebeta': 'google-chrome-beta',
        'curlimpersonate': 'curl-impersonate',
        'vlc': 'vlc',
    }

    def test_multi_word_query_matches_hyphenated_name(self):
        # The reported bug: 'google chrome' found nothing because the raw query was
        # tested against an already-normalized key.
        self.assertIn('google-chrome', naming.match_index_names('google chrome', self.INDEX))

    def test_single_word_query_still_matches(self):
        # Regression guard: this worked before and must keep working.
        matched = naming.match_index_names('chrome', self.INDEX)
        self.assertIn('google-chrome', matched)
        self.assertIn('google-chrome-beta', matched)

    def test_case_and_separator_insensitive(self):
        self.assertIn('google-chrome', naming.match_index_names('Google_Chrome', self.INDEX))

    def test_empty_query_matches_nothing(self):
        self.assertEqual(set(), naming.match_index_names('', self.INDEX))

    def test_empty_index_matches_nothing(self):
        self.assertEqual(set(), naming.match_index_names('chrome', {}))

    def test_none_index_matches_nothing(self):
        self.assertEqual(set(), naming.match_index_names('chrome', None))

    def test_respects_limit(self):
        index = {f'pkg{i}': f'pkg-{i}' for i in range(50)}
        self.assertEqual(5, len(naming.match_index_names('pkg', index, limit=5)))

    def test_default_limit_is_25(self):
        index = {f'pkg{i}': f'pkg-{i}' for i in range(50)}
        self.assertEqual(25, len(naming.match_index_names('pkg', index)))


class MatchInstalledNamesTest(TestCase):

    INSTALLED = {'google-chrome', 'curl-impersonate', 'vlc', 'firefox'}

    def test_multi_word_query_matches(self):
        # The reported bug: controller.py skipped installed matching entirely when the
        # query contained a space, so an installed google-chrome was never considered.
        self.assertEqual({'google-chrome'},
                         naming.match_installed_names('google chrome', self.INSTALLED))

    def test_single_word_query_still_matches(self):
        self.assertEqual({'google-chrome'},
                         naming.match_installed_names('chrome', self.INSTALLED))

    def test_case_insensitive(self):
        self.assertEqual({'firefox'}, naming.match_installed_names('FireFox', self.INSTALLED))

    def test_no_match_returns_empty(self):
        self.assertEqual(set(), naming.match_installed_names('nonexistent', self.INSTALLED))

    def test_empty_query_matches_nothing(self):
        self.assertEqual(set(), naming.match_installed_names('', self.INSTALLED))

    def test_empty_installed_matches_nothing(self):
        self.assertEqual(set(), naming.match_installed_names('chrome', set()))

    def test_none_installed_matches_nothing(self):
        self.assertEqual(set(), naming.match_installed_names('chrome', None))
