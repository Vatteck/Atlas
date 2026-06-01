from unittest import TestCase
from unittest.mock import Mock

from atlas.gems.appimage.controller import AppImageManager
from atlas.gems.arch.controller import ArchManager
from atlas.gems.debian.controller import DebianPackageManager
from atlas.gems.flatpak.controller import FlatpakManager
from atlas.gems.snap.controller import SnapManager
from atlas.gems.web.controller import WebApplicationManager


class GemDefaultEnabledTest(TestCase):
    """Atlas is Arch-focused: the official repo, AUR (both via the arch gem), Flatpak and
    AppImage are enabled by default; Snap/Debian/Web are off by default (still
    re-enableable via Settings). See docs/plans/2026-06-01-source-types-and-multisource-cards.md."""

    def test_arch_relevant_gems_enabled_by_default(self):
        self.assertTrue(ArchManager(context=Mock()).is_default_enabled())
        self.assertTrue(FlatpakManager(context=Mock()).is_default_enabled())
        self.assertTrue(AppImageManager(context=Mock()).is_default_enabled())

    def test_non_arch_gems_disabled_by_default(self):
        self.assertFalse(SnapManager(context=Mock()).is_default_enabled())
        self.assertFalse(DebianPackageManager(context=Mock()).is_default_enabled())
        self.assertFalse(WebApplicationManager(context=Mock()).is_default_enabled())
