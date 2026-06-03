import unittest
from unittest.mock import patch

from atlas.gems.arch import chroot


class ChrootCmdTest(unittest.TestCase):
    DIR = '/var/lib/atlas/aurchroot'

    def test_root_path(self):
        self.assertEqual('/var/lib/atlas/aurchroot/root', chroot.root_path(self.DIR))

    def test_create_root_cmd_defaults_to_base_devel(self):
        cmd = chroot.create_root_cmd(self.DIR)
        self.assertEqual(['mkarchroot', '/var/lib/atlas/aurchroot/root', 'base-devel'], cmd)

    def test_create_root_cmd_with_makepkg_conf_and_packages(self):
        cmd = chroot.create_root_cmd(self.DIR, packages=['base-devel', 'ccache'],
                                     makepkg_conf='/tmp/makepkg.conf')
        # -M must precede the chroot dir; packages come last, in order
        self.assertEqual(['mkarchroot', '-M', '/tmp/makepkg.conf',
                          '/var/lib/atlas/aurchroot/root', 'base-devel', 'ccache'], cmd)

    def test_update_root_cmd(self):
        self.assertEqual(['arch-nspawn', '/var/lib/atlas/aurchroot/root',
                          'pacman', '-Syu', '--noconfirm'], chroot.update_root_cmd(self.DIR))

    def test_build_cmd_minimal(self):
        # clean defaults on; no namcap; no injection
        self.assertEqual(['makechrootpkg', '-r', self.DIR, '-c'], chroot.build_cmd(self.DIR))

    def test_build_cmd_without_clean(self):
        self.assertEqual(['makechrootpkg', '-r', self.DIR], chroot.build_cmd(self.DIR, clean=False))

    def test_build_cmd_injects_each_dep_with_its_own_flag(self):
        cmd = chroot.build_cmd(self.DIR, inject_pkgs=['/b/dep1.pkg.tar.zst', '/b/dep2.pkg.tar.zst'])
        self.assertEqual(['makechrootpkg', '-r', self.DIR, '-c',
                          '-I', '/b/dep1.pkg.tar.zst', '-I', '/b/dep2.pkg.tar.zst'], cmd)

    def test_build_cmd_forwards_makepkg_args_after_double_dash(self):
        cmd = chroot.build_cmd(self.DIR, namcap=True, makepkg_args=['--skipchecksums'])
        self.assertEqual(['makechrootpkg', '-r', self.DIR, '-c', '-n', '--', '--skipchecksums'], cmd)

    def test_build_cmd_no_double_dash_when_no_makepkg_args(self):
        self.assertNotIn('--', chroot.build_cmd(self.DIR, makepkg_args=[]))


class ChrootAvailabilityTest(unittest.TestCase):
    def test_available_true_when_all_present(self):
        with patch.object(chroot.shutil, 'which', side_effect=lambda b: f'/usr/bin/{b}'):
            self.assertTrue(chroot.available())
            self.assertEqual([], chroot.missing_tools())

    def test_available_false_and_reports_missing(self):
        present = {'makechrootpkg', 'arch-nspawn'}  # mkarchroot missing
        with patch.object(chroot.shutil, 'which', side_effect=lambda b: f'/usr/bin/{b}' if b in present else None):
            self.assertFalse(chroot.available())
            self.assertEqual(['mkarchroot'], chroot.missing_tools())

    def test_root_exists(self):
        with patch.object(chroot.os.path, 'isdir', return_value=True) as m:
            self.assertTrue(chroot.root_exists('/x'))
            m.assert_called_once_with('/x/root')


if __name__ == '__main__':
    unittest.main()
