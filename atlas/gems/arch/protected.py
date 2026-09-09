import os
from typing import Callable, Optional, Set

from atlas.gems.arch import pacman

MODULES_DIR = '/usr/lib/modules'

# The virtual name every initramfs generator provides (mkinitcpio, dracut, booster). Without
# one, a kernel install cannot produce a bootable image.
INITRAMFS = 'initramfs'


def resolve_protected(kernel_release: str,
                      owner_of_path: Callable[[str], Optional[str]],
                      providers_of: Callable[[str], Set[str]]) -> Set[str]:
    """Packages that must never be removed as a side effect of an upgrade.

    Derived from the live system rather than hardcoded, so it holds on any Arch-based
    distribution: the package owning the running kernel's modules directory, and whatever
    provides the initramfs. Lookups are injected so this stays testable without a real system.
    """
    protected = set()

    kernel_owner = owner_of_path(f'{MODULES_DIR}/{kernel_release}')
    if kernel_owner:
        protected.add(kernel_owner)

    protected.update(p for p in (providers_of(INITRAMFS) or ()) if p)

    return protected


def system_protected() -> Set[str]:
    """resolve_protected() wired to the live system: the running kernel release, pacman's
    file-owner lookup, and its provided-names map."""
    release = os.uname().release
    owners = pacman.map_owners([f'{MODULES_DIR}/{release}']) or {}
    provided = pacman.map_provided() or {}

    return resolve_protected(kernel_release=release,
                             owner_of_path=owners.get,
                             providers_of=provided.get)
