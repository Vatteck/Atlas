import json
import os
from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock

from atlas.gems.flatpak import flathub

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_fixture():
    with open(os.path.join(FILE_DIR, 'resources', 'flathub_v2_appstream_gimp.json')) as f:
        return json.load(f)


class FlathubV2Test(TestCase):

    def setUp(self):
        self.data = _load_fixture()

    # --- get_appstream (the only I/O) -------------------------------------
    def test_get_appstream_hits_v2_appstream_endpoint(self):
        client = Mock()
        client.get_json.return_value = {'id': 'x'}

        result = flathub.get_appstream(client, 'org.gimp.GIMP')

        client.get_json.assert_called_once_with('https://flathub.org/api/v2/appstream/org.gimp.GIMP')
        self.assertEqual({'id': 'x'}, result)

    def test_get_appstream_none_id(self):
        client = Mock()
        self.assertIsNone(flathub.get_appstream(client, ''))
        client.get_json.assert_not_called()

    # --- latest_release ---------------------------------------------------
    def test_latest_release_returns_first(self):
        self.assertEqual('3.2.4', flathub.latest_release(self.data).get('version'))

    def test_latest_release_handles_missing(self):
        self.assertEqual({}, flathub.latest_release(None))
        self.assertEqual({}, flathub.latest_release({}))
        self.assertEqual({}, flathub.latest_release({'releases': []}))

    # --- categories (v2 = list of strings) --------------------------------
    def test_categories_are_strings(self):
        self.assertEqual(['Graphics', '2DGraphics', 'RasterGraphics'], flathub.categories(self.data))

    def test_categories_missing(self):
        self.assertEqual([], flathub.categories({}))
        self.assertEqual([], flathub.categories(None))

    # --- screenshot_urls (pick widest src) --------------------------------
    def test_screenshot_urls_picks_widest_source(self):
        urls = flathub.screenshot_urls(self.data)
        self.assertTrue(urls)
        self.assertTrue(all(u.startswith('https://') for u in urls))

    def test_screenshot_urls_picks_largest_width(self):
        data = {'screenshots': [{'sizes': [
            {'width': '500', 'src': 'small.png'},
            {'width': '1920', 'src': 'big.png'},
            {'width': '800', 'src': 'mid.png'},
        ]}]}
        self.assertEqual(['big.png'], flathub.screenshot_urls(data))

    def test_screenshot_urls_skips_sizeless_and_handles_bad_width(self):
        data = {'screenshots': [
            {'sizes': []},                                   # no sizes -> skipped
            {'sizes': [{'width': None, 'src': 'a.png'}]},    # bad width still yields a src
        ]}
        self.assertEqual(['a.png'], flathub.screenshot_urls(data))

    def test_screenshot_urls_empty(self):
        self.assertEqual([], flathub.screenshot_urls({}))
        self.assertEqual([], flathub.screenshot_urls(None))

    # --- app_info (curated panel dict) ------------------------------------
    def test_app_info_maps_v2_fields(self):
        info = flathub.app_info(self.data)
        self.assertEqual('GNU Image Manipulation Program', info['name'])
        self.assertEqual('3.2.4', info['version'])
        self.assertEqual('The GIMP team', info['developer'])
        self.assertEqual('Graphics, 2DGraphics, RasterGraphics', info['categories'])
        self.assertIn('homepage', info)
        self.assertIsInstance(info['release_date'], datetime)
        # description must be HTML-stripped
        self.assertNotIn('<', info['description'])

    def test_app_info_drops_empty_values(self):
        info = flathub.app_info({'name': 'X', 'summary': '', 'releases': []})
        self.assertEqual({'name': 'X'}, info)

    def test_app_info_empty(self):
        self.assertEqual({}, flathub.app_info(None))
        self.assertEqual({}, flathub.app_info({}))

    def test_release_date_from_iso_when_no_timestamp(self):
        info = flathub.app_info({'name': 'X', 'releases': [{'version': '1', 'date': '2024-05-01'}]})
        self.assertEqual(datetime(2024, 5, 1), info['release_date'])
