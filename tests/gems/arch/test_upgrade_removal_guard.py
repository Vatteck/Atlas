from unittest import TestCase
from unittest.mock import MagicMock, patch

from atlas.gems.arch.controller import ArchManager


def _stub_manager():
    """The attributes _remove_transaction_packages actually reads. Calling the method
    unbound keeps this focused on the guard rather than on constructing an ArchManager."""
    stub = MagicMock()
    stub.logger = MagicMock()
    stub.i18n = {
        'error': 'error',
        'arch.upgrade.error.remove_refused': '{} / {}',
        'arch.upgrade.error.remove_protected': '{}',
    }
    return stub


class UpgradeRemovalGuardTest(TestCase):
    """Update All must never remove a package the system needs in order to boot.

    On 2026-09-09 it removed linux-cachyos, mkinitcpio and limine-mkinitcpio-hook. The
    existing guard is reverse-dependency based and could not catch it: nothing depends on a
    kernel, so it is a leaf and passed the check.
    """

    def test_refuses_to_remove_a_protected_package(self):
        handler = MagicMock()

        with patch('atlas.gems.arch.pacman.map_required_by', return_value={}), \
             patch('atlas.gems.arch.protected.system_protected', return_value={'linux-cachyos'}), \
             patch('atlas.gems.arch.pacman.remove_several') as remove_several:
            result = ArchManager._remove_transaction_packages(_stub_manager(),
                                                              to_remove={'linux-cachyos'},
                                                              handler=handler,
                                                              root_password=None)

        self.assertFalse(result, 'the removal must not be reported as successful')
        remove_several.assert_not_called()

    def test_allows_an_ordinary_leaf_package_through(self):
        # The guard must not block legitimate removals — over-blocking would break upgrades.
        handler = MagicMock()
        handler.handle_simple.return_value = (True, '')

        with patch('atlas.gems.arch.pacman.map_required_by', return_value={}), \
             patch('atlas.gems.arch.protected.system_protected', return_value={'linux-cachyos'}), \
             patch('atlas.gems.arch.pacman.clear_caches'), \
             patch('atlas.gems.arch.pacman.remove_several') as remove_several:
            result = ArchManager._remove_transaction_packages(_stub_manager(),
                                                              to_remove={'some-old-font'},
                                                              handler=handler,
                                                              root_password=None)

        self.assertTrue(result)
        remove_several.assert_called_once()
