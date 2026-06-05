import warnings
from unittest import TestCase
from unittest.mock import Mock, patch

from atlas.gems.arch.controller import ArchManager
from atlas.gems.arch.mapper import AURDataMapper


class ListAurPackagesTest(TestCase):
    """ArchManager.list_aur_packages: maps RPC-shaped discovery entries to ArchPackage objects and
    marks installed state via one cheap `pacman -Q` (no read_installed)."""

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore', category=DeprecationWarning)

    def _manager(self):
        # Build a bare ArchManager without running __init__ (which needs a full context); wire only
        # the attributes list_aur_packages touches.
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.categories = {}
        mgr.aur_mapper = AURDataMapper(http_client=Mock(), i18n={}, logger=Mock())
        return mgr

    def _entries(self):
        # FirstSubmitted is present on real meta-dump entries (and the generator keeps it).
        return [
            {'Name': 'yay', 'Version': '12.1.0-1', 'NumVotes': 2000, 'Popularity': 40.0, 'FirstSubmitted': 1},
            {'Name': 'paru', 'Version': '2.0.0-1', 'NumVotes': 1000, 'Popularity': 30.0, 'FirstSubmitted': 1},
            {'Name': 'some-bin', 'Version': '1.0-1', 'NumVotes': 5, 'Popularity': 1.0, 'FirstSubmitted': 1},
        ]

    def test_marks_installed_and_update(self):
        mgr = self._manager()
        # yay installed but behind; some-bin installed and current; paru not installed
        installed = {'yay': '12.0.0-1', 'some-bin': '1.0-1'}
        with patch('atlas.gems.arch.pacman.map_installed', return_value=installed):
            pkgs = mgr.list_aur_packages(self._entries())

        by_name = {p.name: p for p in pkgs}
        self.assertEqual(3, len(pkgs))

        self.assertTrue(by_name['yay'].installed)
        self.assertEqual('12.0.0-1', by_name['yay'].version)       # installed version kept
        self.assertEqual('12.1.0-1', by_name['yay'].latest_version)  # AUR version
        self.assertTrue(by_name['yay'].update)                      # behind → Update

        self.assertTrue(by_name['some-bin'].installed)
        self.assertFalse(by_name['some-bin'].update)               # current → no update

        self.assertFalse(by_name['paru'].installed)               # not installed → Install

    def test_fails_open_when_pacman_errors(self):
        mgr = self._manager()
        with patch('atlas.gems.arch.pacman.map_installed', side_effect=RuntimeError('boom')):
            pkgs = mgr.list_aur_packages(self._entries())
        # nothing marked installed, but the list still maps
        self.assertEqual(3, len(pkgs))
        self.assertTrue(all(not p.installed for p in pkgs))

    def test_empty_and_malformed_entries(self):
        mgr = self._manager()
        with patch('atlas.gems.arch.pacman.map_installed', return_value={}):
            self.assertEqual([], mgr.list_aur_packages([]))
            pkgs = mgr.list_aur_packages([{'Name': 'ok', 'Version': '1-1', 'FirstSubmitted': 1}, {}, {'NoName': 'x'}])
        self.assertEqual(['ok'], [p.name for p in pkgs])
