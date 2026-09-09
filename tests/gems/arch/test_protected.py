import os
from unittest import TestCase
from unittest.mock import patch

from atlas.gems.arch import protected


class ResolveProtectedTest(TestCase):
    """The package set that must never be removed as a side effect of an upgrade.

    Derived from the live system rather than hardcoded to one distribution: the package
    owning the running kernel's modules, plus whatever provides the initramfs.
    """

    def test_protects_the_package_owning_the_running_kernel(self):
        # The incident this guards against: Update All removed linux-cachyos while it was
        # the running kernel. Nothing depends on a kernel, so the reverse-dependency guard
        # could never catch it.
        owners = {'/usr/lib/modules/7.1.8-1-cachyos': 'linux-cachyos'}

        result = protected.resolve_protected(kernel_release='7.1.8-1-cachyos',
                                             owner_of_path=owners.get,
                                             providers_of=lambda name: set())

        self.assertIn('linux-cachyos', result)

    def test_protects_whatever_provides_the_initramfs(self):
        # mkinitcpio was removed in the same transaction. It is a leaf too, and without an
        # initramfs generator the next kernel install cannot produce a bootable image.
        providers = {'initramfs': {'mkinitcpio'}}

        result = protected.resolve_protected(kernel_release='7.1.8-1-cachyos',
                                             owner_of_path=lambda path: None,
                                             providers_of=providers.get)

        self.assertIn('mkinitcpio', result)

    def test_does_not_protect_unrelated_packages_that_merely_look_kernel_ish(self):
        # A guard that over-blocks is its own failure: it would stop legitimate upgrades.
        # 'linux-wallpaperengine-git' and 'linux-firmware' are real packages on the affected
        # machine; neither owns the boot path. Naive `name.startswith('linux')` matching would
        # wrongly protect both, so this pins the derived-not-guessed approach.
        owners = {'/usr/lib/modules/7.1.8-1-cachyos': 'linux-cachyos'}

        result = protected.resolve_protected(kernel_release='7.1.8-1-cachyos',
                                             owner_of_path=owners.get,
                                             providers_of=lambda name: {'mkinitcpio'})

        self.assertNotIn('linux-wallpaperengine-git', result)
        self.assertNotIn('linux-firmware', result)


class SystemProtectedTest(TestCase):
    """The thin wiring from the live system into resolve_protected()."""

    def test_resolves_against_the_running_kernel_release(self):
        # Asserted on the returned set rather than on the calls: if the modules path were
        # built from anything but the running release, the owner lookup would miss and
        # 'my-kernel' would be absent.
        running = os.uname().release

        with patch('atlas.gems.arch.pacman.map_owners',
                   return_value={f'/usr/lib/modules/{running}': 'my-kernel'}), \
             patch('atlas.gems.arch.pacman.map_provided',
                   return_value={'initramfs': {'mkinitcpio'}}):
            result = protected.system_protected()

        self.assertEqual({'my-kernel', 'mkinitcpio'}, result)

    def test_survives_a_system_with_no_owning_package(self):
        # A custom-compiled kernel, or a container, owns nothing. Must not raise: the
        # confirmation dialog is the backstop in that case, not a crash.
        with patch('atlas.gems.arch.pacman.map_owners', return_value={}), \
             patch('atlas.gems.arch.pacman.map_provided', return_value=None):
            result = protected.system_protected()

        self.assertEqual(set(), result)
