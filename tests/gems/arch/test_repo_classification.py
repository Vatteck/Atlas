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

    def _fill(self, repo_pkgs, repo_map, aur_index=None):
        with patch('atlas.gems.arch.controller.pacman.map_repositories', return_value=repo_map), \
             patch('atlas.gems.arch.controller.pacman.list_repository_updates', return_value={}):
            pkgs = []
            self.mgr._fill_repo_pkgs(repo_pkgs, pkgs, aur_index, disk_loader=None)
            return {p.name: p for p in pkgs}

    def test_foreign_package_not_in_any_repo_is_labeled_aur(self):
        # pacman -Si finds nothing -> repo_map empty -> pkgrepo None (the atlas-pm-git case)
        pkgs = self._fill({'atlas-pm-git': {'version': '1.0'}}, repo_map={}, aur_index={'yay', 'paru'})
        pkg = pkgs['atlas-pm-git']
        self.assertEqual('aur', pkg.repository)          # NOT None/arch_repo
        self.assertEqual('aur', pkg.get_type())          # frontend would show "AUR", not "Arch"
        self.assertIn('Removed from AUR', pkg.categories)  # flagged: missing from the (stale) index

    def test_foreign_package_present_in_index_is_aur_without_removed_flag(self):
        pkgs = self._fill({'atlas-pm-git': {'version': '1.0'}}, repo_map={}, aur_index={'atlas-pm-git'})
        pkg = pkgs['atlas-pm-git']
        self.assertEqual('aur', pkg.repository)
        self.assertNotIn('Removed from AUR', pkg.categories)

    def test_genuine_repo_package_keeps_its_repo(self):
        pkgs = self._fill({'firefox': {'version': '1.0'}}, repo_map={'firefox': 'extra'})
        pkg = pkgs['firefox']
        self.assertEqual('extra', pkg.repository)
        self.assertEqual('arch_repo', pkg.get_type())    # real repo package -> "Arch" is correct


if __name__ == '__main__':
    unittest.main()
