import unittest
from unittest.mock import Mock, patch

from atlas.gems.arch.controller import ArchManager


class ChrootBuildWiringTest(unittest.TestCase):
    """ArchManager._build_in_chroot: lifecycle decisions + host-build fallback.

    The process layer is stubbed at `_chroot_root_proc` (its argv is covered by test_chroot.py);
    these tests assert *which* steps run and how the build user is chosen."""

    def setUp(self):
        self.mgr = ArchManager.__new__(ArchManager)  # skip heavy __init__
        self.mgr.logger = Mock()
        self.mgr.pkgbuilder_user = 'atlas-aur'
        self.mgr.i18n = {'arch.building.package': 'Building {}'}
        self.mgr.add_package_builder_user = Mock(return_value=True)
        self.mgr._chroot_root_proc = Mock()

    def _ctx(self, root_user=True):
        self.mgr.context = Mock(root_user=root_user)  # manager-level app context (has root_user)
        ctx = Mock()
        ctx.name = 'foo'
        ctx.project_dir = '/build/foo'
        ctx.root_password = None if root_user else 'pw'
        ctx.config = {'aur_build_chroot': True}
        ctx.chroot_inject_dir = None   # no AUR deps to inject in these wiring tests
        ctx.watcher = Mock()
        ctx.handler = Mock()
        return ctx

    def test_falls_back_when_devtools_missing(self):
        ctx = self._ctx()
        with patch('atlas.gems.arch.controller.chroot.available', return_value=False), \
             patch('atlas.gems.arch.controller.chroot.missing_tools', return_value=['makechrootpkg']):
            self.assertIsNone(self.mgr._build_in_chroot(ctx, optimize=False))
        self.mgr._chroot_root_proc.assert_not_called()  # nothing executed

    def test_creates_root_when_absent_then_builds(self):
        ctx = self._ctx()
        self.mgr._chroot_root_proc.side_effect = [(True, 'mkdir'), (True, 'made'), (True, 'built')]  # mkdir, create, build
        with patch('atlas.gems.arch.controller.chroot.available', return_value=True), \
             patch('atlas.gems.arch.controller.chroot.root_exists', return_value=False), \
             patch('atlas.gems.arch.controller.chroot.create_root_cmd', return_value=['mkarchroot']) as mk, \
             patch('atlas.gems.arch.controller.chroot.build_cmd', return_value=['makechrootpkg']) as bc:
            result = self.mgr._build_in_chroot(ctx, optimize=False)
        self.assertEqual((True, 'built'), result)
        mk.assert_called_once()                                   # root created (was absent)
        self.assertEqual('atlas-aur', bc.call_args.kwargs['makepkg_user'])   # -U passed when root
        self.assertEqual(3, self.mgr._chroot_root_proc.call_count)           # mkdir + create + build, no update
        # the parent dir is created before mkarchroot (mkarchroot's readlink -f needs it)
        self.assertEqual(['mkdir', '-p', '/var/lib/atlas/aurchroot'],
                         self.mgr._chroot_root_proc.call_args_list[0].args[1])
        self.assertEqual('/build/foo', self.mgr._chroot_root_proc.call_args.kwargs['cwd'])  # built in pkg dir

    def test_updates_root_when_present(self):
        ctx = self._ctx()
        self.mgr._chroot_root_proc.side_effect = [(True, 'updated'), (True, 'built')]
        with patch('atlas.gems.arch.controller.chroot.available', return_value=True), \
             patch('atlas.gems.arch.controller.chroot.root_exists', return_value=True), \
             patch('atlas.gems.arch.controller.chroot.update_root_cmd', return_value=['arch-nspawn']) as up, \
             patch('atlas.gems.arch.controller.chroot.create_root_cmd') as mk, \
             patch('atlas.gems.arch.controller.chroot.build_cmd', return_value=['makechrootpkg']):
            result = self.mgr._build_in_chroot(ctx, optimize=False)
        self.assertEqual((True, 'built'), result)
        up.assert_called_once()
        mk.assert_not_called()                                    # root present -> no create

    def test_falls_back_when_root_creation_fails(self):
        ctx = self._ctx()
        self.mgr._chroot_root_proc.side_effect = [(True, 'mkdir'), (False, 'mkarchroot blew up')]
        with patch('atlas.gems.arch.controller.chroot.available', return_value=True), \
             patch('atlas.gems.arch.controller.chroot.root_exists', return_value=False), \
             patch('atlas.gems.arch.controller.chroot.create_root_cmd', return_value=['mkarchroot']), \
             patch('atlas.gems.arch.controller.chroot.build_cmd') as bc:
            self.assertIsNone(self.mgr._build_in_chroot(ctx, optimize=False))
        bc.assert_not_called()                                    # never reached the build

    def test_injects_built_aur_deps_from_inject_dir(self):
        ctx = self._ctx()
        ctx.chroot_inject_dir = '/build/inject'
        self.mgr._chroot_root_proc.side_effect = [(True, 'updated'), (True, 'built')]
        deps = ['/build/inject/dep1.pkg.tar.zst', '/build/inject/dep2.pkg.tar.zst']
        with patch('atlas.gems.arch.controller.chroot.available', return_value=True), \
             patch('atlas.gems.arch.controller.chroot.root_exists', return_value=True), \
             patch('atlas.gems.arch.controller.chroot.update_root_cmd', return_value=['arch-nspawn']), \
             patch('atlas.gems.arch.controller.chroot.build_cmd', return_value=['makechrootpkg']) as bc, \
             patch('atlas.gems.arch.controller.os.path.isdir', return_value=True), \
             patch('atlas.gems.arch.controller.glob.glob', return_value=deps):
            self.mgr._build_in_chroot(ctx, optimize=False)
        self.assertEqual(deps, bc.call_args.kwargs['inject_pkgs'])  # built deps fed to makechrootpkg -I

    def test_unprivileged_omits_build_user(self):
        ctx = self._ctx(root_user=False)
        self.mgr._chroot_root_proc.side_effect = [(True, 'updated'), (True, 'built')]
        with patch('atlas.gems.arch.controller.chroot.available', return_value=True), \
             patch('atlas.gems.arch.controller.chroot.root_exists', return_value=True), \
             patch('atlas.gems.arch.controller.chroot.update_root_cmd', return_value=['arch-nspawn']), \
             patch('atlas.gems.arch.controller.chroot.build_cmd', return_value=['makechrootpkg']) as bc:
            self.mgr._build_in_chroot(ctx, optimize=False)
        self.assertIsNone(bc.call_args.kwargs['makepkg_user'])    # rely on SUDO_USER, no -U
        self.mgr.add_package_builder_user.assert_not_called()     # only the root path creates a user


class ChrootInjectDirPropagationTest(unittest.TestCase):
    """Dep contexts must share the parent's inject dir so a dep's stashed output is visible when the
    dependent builds."""

    def test_clone_base_propagates_inject_dir(self):
        from atlas.gems.arch.controller import TransactionContext
        parent = TransactionContext(aur_supported=True, arch_config={})
        parent.chroot_inject_dir = '/build/inject_123'
        child = parent.clone_base()
        self.assertEqual('/build/inject_123', child.chroot_inject_dir)

    def test_gen_dep_context_inherits_inject_dir(self):
        from atlas.gems.arch.controller import TransactionContext
        parent = TransactionContext(aur_supported=True, arch_config={})
        parent.chroot_inject_dir = '/build/inject_123'
        dep = parent.gen_dep_context('libfoo', 'aur')
        self.assertEqual('/build/inject_123', dep.chroot_inject_dir)
        self.assertTrue(dep.dependency)


if __name__ == '__main__':
    unittest.main()
