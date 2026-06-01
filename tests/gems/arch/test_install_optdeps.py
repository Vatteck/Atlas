from logging import getLogger
from unittest import TestCase
from unittest.mock import MagicMock

from atlas.gems.arch.controller import ArchManager


def _bare_manager() -> ArchManager:
    # ArchManager.__init__ wires up a lot of collaborators we don't need here; build a
    # bare instance and attach only what _install_from_repository / _install_from_aur use.
    man = ArchManager.__new__(ArchManager)
    man.logger = getLogger('test')
    man.logger.disabled = True
    man._update_progress = MagicMock()
    man._handle_missing_deps = MagicMock(return_value=True)
    man._save_pkgbuild = MagicMock()
    man._update_aur_index = MagicMock()
    return man


def _ctx():
    ctx = MagicMock()
    ctx.skip_opt_deps = False
    ctx.dependency = False
    ctx.update_aur_index = False
    ctx.name = 'gimp'
    return ctx


class InstallOptdepsDoNotFailMainTest(TestCase):
    """Optional dependencies are optional: a failure/cancellation while handling them
    must never flip the (already successful) main package install into a failure.
    Regression for 'install succeeds but the operation reports failed'."""

    def test_repository__optdeps_returning_false_does_not_fail_main_install(self):
        man = _bare_manager()
        man._install = MagicMock(return_value=True)
        man._install_optdeps = MagicMock(return_value=False)  # e.g. map_missing_deps cancelled

        self.assertTrue(man._install_from_repository(_ctx()))
        man._install_optdeps.assert_called_once()

    def test_repository__optdeps_raising_does_not_fail_main_install(self):
        man = _bare_manager()
        man._install = MagicMock(return_value=True)
        man._install_optdeps = MagicMock(side_effect=RuntimeError('boom'))

        self.assertTrue(man._install_from_repository(_ctx()))

    def test_repository__main_install_failure_still_fails(self):
        man = _bare_manager()
        man._install = MagicMock(return_value=False)
        man._install_optdeps = MagicMock(return_value=True)

        self.assertFalse(man._install_from_repository(_ctx()))
        man._install_optdeps.assert_not_called()

    def test_repository__missing_required_deps_still_fails(self):
        man = _bare_manager()
        man._handle_missing_deps = MagicMock(return_value=False)
        man._install = MagicMock(return_value=True)
        man._install_optdeps = MagicMock(return_value=True)

        self.assertFalse(man._install_from_repository(_ctx()))
        man._install.assert_not_called()
