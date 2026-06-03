import unittest
from unittest.mock import Mock, patch

from atlas.gems.arch.controller import ArchManager


class FillRepoPkgsClassificationTest(unittest.TestCase):
    """Regression: an installed foreign (AUR-only) package must be labeled 'aur', not arch_repo.
    Repro was atlas-pm-git showing a two-source 'Arch + AUR' card."""

    def setUp(self):
        self.mgr = ArchManager.__new__(ArchManager)  # skip heavy __init__
        self.mgr.logger = Mock()
        self.mgr.categories = {}
        self.mgr.i18n = {'arch.category.remove_from_aur': 'Removed from AUR'}

    def _fill(self, repo_pkgs, repo_map, removed_from_aur=None):
        with patch('atlas.gems.arch.controller.pacman.map_repositories', return_value=repo_map), \
             patch('atlas.gems.arch.controller.pacman.list_repository_updates', return_value={}):
            pkgs = []
            self.mgr._fill_repo_pkgs(repo_pkgs, pkgs, removed_from_aur or set(), disk_loader=None)
            return {p.name: p for p in pkgs}

    def test_foreign_package_not_in_any_repo_is_labeled_aur(self):
        # pacman -Si finds nothing -> repo_map empty -> pkgrepo None (the atlas-pm-git case)
        pkgs = self._fill({'atlas-pm-git': {'version': '1.0'}}, repo_map={})
        pkg = pkgs['atlas-pm-git']
        self.assertEqual('aur', pkg.repository)          # NOT None/arch_repo
        self.assertEqual('aur', pkg.get_type())          # frontend would show "AUR", not "Arch"

    def test_removed_flag_only_when_confirmed_removed(self):
        pkgs = self._fill({'atlas-pm-git': {'version': '1.0'}}, repo_map={},
                          removed_from_aur={'atlas-pm-git'})
        self.assertIn('Removed from AUR', pkgs['atlas-pm-git'].categories)

    def test_no_removed_flag_when_not_confirmed(self):
        # foreign + still 'aur', but NOT in the confirmed-removed set (stale index → no false flag)
        pkgs = self._fill({'atlas-pm-git': {'version': '1.0'}}, repo_map={}, removed_from_aur=set())
        self.assertEqual('aur', pkgs['atlas-pm-git'].repository)
        self.assertNotIn('Removed from AUR', pkgs['atlas-pm-git'].categories)

    def test_genuine_repo_package_keeps_its_repo(self):
        pkgs = self._fill({'firefox': {'version': '1.0'}}, repo_map={'firefox': 'extra'})
        pkg = pkgs['firefox']
        self.assertEqual('extra', pkg.repository)
        self.assertEqual('arch_repo', pkg.get_type())    # real repo package -> "Arch" is correct


class ConfirmRemovedFromAurTest(unittest.TestCase):
    """_confirm_removed_from_aur: verify index-misses against the live RPC (fix stale-index false flags)."""

    def setUp(self):
        self.mgr = ArchManager.__new__(ArchManager)
        self.mgr.logger = Mock()
        self.mgr.aur_client = Mock()

    def test_present_on_aur_is_not_removed(self):
        # RPC confirms the package exists (index was just stale) → not flagged removed
        self.mgr.aur_client.get_info.return_value = [{'Name': 'atlas-pm-git'}]
        self.assertEqual(set(), self.mgr._confirm_removed_from_aur(['atlas-pm-git']))

    def test_absent_on_aur_is_removed(self):
        # RPC succeeds and returns none of them → genuinely removed
        self.mgr.aur_client.get_info.return_value = []
        self.assertEqual({'gone-pkg'}, self.mgr._confirm_removed_from_aur(['gone-pkg']))

    def test_rpc_failure_flags_nothing(self):
        self.mgr.aur_client.get_info.return_value = None  # offline / RPC error → uncertain
        self.assertEqual(set(), self.mgr._confirm_removed_from_aur(['atlas-pm-git']))

    def test_mixed(self):
        self.mgr.aur_client.get_info.return_value = [{'Name': 'real-aur-pkg'}]
        self.assertEqual({'gone-pkg'},
                         self.mgr._confirm_removed_from_aur(['real-aur-pkg', 'gone-pkg']))


if __name__ == '__main__':
    unittest.main()
