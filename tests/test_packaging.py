"""Packaging guards (Tier 2).

The desktop entry + app icons are installed by the Arch PKGBUILDs, not the wheel, so the existing CI
layout check can't see them — yet a malformed .desktop or a missing/renamed icon is exactly what
caused the KDE "map icon" bug. These checks are cheap and portable: the install *sources* exist, both
PKGBUILDs install the scalable SVG + PNG + desktop file, and (where the tool is available) the
desktop file validates.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

import atlas

ATLAS_DIR = Path(atlas.__file__).resolve().parent
REPO_ROOT = ATLAS_DIR.parent

DESKTOP_FILE = ATLAS_DIR / 'desktop' / 'atlas-pm.desktop'
LOGO_SVG = ATLAS_DIR / 'view' / 'resources' / 'img' / 'logo.svg'
LOGO_PNG = ATLAS_DIR / 'view' / 'resources' / 'img' / 'logo.png'
PKGBUILDS = [REPO_ROOT / 'linux_dist' / 'arch' / 'PKGBUILD',
             REPO_ROOT / 'linux_dist' / 'arch' / 'release' / 'PKGBUILD']


class PackagingSourcesTest(unittest.TestCase):
    def test_install_sources_exist(self):
        for f in (DESKTOP_FILE, LOGO_SVG, LOGO_PNG):
            self.assertTrue(f.is_file(), f"missing packaging source: {f}")

    def test_desktop_file_identity(self):
        txt = DESKTOP_FILE.read_text()
        # The whole identity is 'atlas-pm' (matches the runtime app_id from set_prgname); a bare
        # 'atlas' would collide with a theme's generic map icon.
        self.assertIn('Icon=atlas-pm', txt)
        self.assertIn('StartupWMClass=atlas-pm', txt)

    def test_both_pkgbuilds_install_svg_png_and_desktop(self):
        for pkg in PKGBUILDS:
            self.assertTrue(pkg.is_file(), f"missing PKGBUILD: {pkg}")
            txt = pkg.read_text()
            self.assertIn('hicolor/scalable/apps/atlas-pm.svg', txt,
                          f"{pkg} no longer installs the scalable SVG icon")
            self.assertIn('512x512/apps/atlas-pm.png', txt,
                          f"{pkg} no longer installs the PNG icon")
            self.assertIn('applications/atlas-pm.desktop', txt,
                          f"{pkg} no longer installs the desktop entry")


@unittest.skipUnless(shutil.which('desktop-file-validate'),
                     'desktop-file-validate not installed')
class DesktopFileValidateTest(unittest.TestCase):
    def test_desktop_file_validates(self):
        res = subprocess.run(['desktop-file-validate', str(DESKTOP_FILE)],
                             capture_output=True, text=True)
        self.assertEqual(0, res.returncode,
                         f"desktop-file-validate failed:\n{res.stdout}{res.stderr}")


if __name__ == '__main__':
    unittest.main()
