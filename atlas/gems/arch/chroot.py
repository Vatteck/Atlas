"""Clean-chroot AUR building via Arch's `devtools` (makechrootpkg / mkarchroot / arch-nspawn).

Builds an AUR package inside an nspawn chroot instead of against the live host — the same approach
`paru` and `aurutils` use. This isolates the **build** (`prepare()/build()/package()` can't scribble
on your `$HOME`/system) and enforces dependency correctness (minimal build env).

**It does NOT make a malicious *package* safe:** the resulting `.pkg.tar.zst` is still installed on
the host with pacman and its `.install` scriptlets run as root. Pair this with the PKGBUILD review;
do not present it as supply-chain immunity. See docs/plans/2026-06-02-sandboxed-aur-builds.md.

This module is pure command construction + a preconditions check (no process execution); the
controller wires it into the build step, with a fallback to the host build when it's unavailable.
"""
import os
import shutil
from typing import Iterable, List, Optional

# devtools binaries we depend on.
MAKECHROOTPKG = 'makechrootpkg'
MKARCHROOT = 'mkarchroot'
ARCH_NSPAWN = 'arch-nspawn'

# Default chroot location (a dedicated dir; the base copy is ~hundreds of MB). Overridable via config.
DEFAULT_CHROOT_DIR = '/var/lib/atlas/aurchroot'

# Base package set installed into the chroot root (clean-chroot building needs base-devel).
BASE_PACKAGES = ('base-devel',)


def available() -> bool:
    """True only if the full clean-chroot toolchain is installed (all three devtools binaries)."""
    return all(shutil.which(b) for b in (MAKECHROOTPKG, MKARCHROOT, ARCH_NSPAWN))


def missing_tools() -> List[str]:
    """Which of the required devtools binaries are absent (for a precise 'install devtools' notice)."""
    return [b for b in (MAKECHROOTPKG, MKARCHROOT, ARCH_NSPAWN) if not shutil.which(b)]


def root_path(chroot_dir: str) -> str:
    """The chroot's base copy. `makechrootpkg` builds in throwaway copies cloned from `<dir>/root`."""
    return os.path.join(chroot_dir, 'root')


def root_exists(chroot_dir: str) -> bool:
    """Whether the chroot has already been created (its root copy is present)."""
    return os.path.isdir(root_path(chroot_dir))


def create_root_cmd(chroot_dir: str, packages: Optional[Iterable[str]] = None,
                    makepkg_conf: Optional[str] = None) -> List[str]:
    """`mkarchroot [-M makepkg.conf] <chrootdir>/root <packages...>` — one-time chroot creation."""
    cmd = [MKARCHROOT]
    if makepkg_conf:
        cmd += ['-M', makepkg_conf]
    cmd.append(root_path(chroot_dir))
    cmd += list(packages) if packages else list(BASE_PACKAGES)
    return cmd


def update_root_cmd(chroot_dir: str) -> List[str]:
    """`arch-nspawn <chrootdir>/root pacman -Syu --noconfirm` — refresh the chroot before a build so
    it builds against current packages (and picks up the configured mirrors)."""
    return [ARCH_NSPAWN, root_path(chroot_dir), 'pacman', '-Syu', '--noconfirm']


def build_cmd(chroot_dir: str, inject_pkgs: Optional[Iterable[str]] = None, clean: bool = True,
              namcap: bool = False, makepkg_user: Optional[str] = None,
              makepkg_args: Optional[Iterable[str]] = None) -> List[str]:
    """`makechrootpkg -r <chrootdir> [-U <user>] [-c] [-n] [-I <pkg> ...] [-- <makepkg args>]`, run
    in the package directory.

    - `-r <chrootdir>`: the chroot to build in (a copy of `<chrootdir>/root` is used).
    - `-U <user>`: run the inner `makepkg` as this (unprivileged) user. **Required when we invoke
      makechrootpkg as root directly**, because it otherwise defaults makepkg's user to `$USER`
      (root) and refuses to build ("Running makepkg as root is not allowed"). Must be a real,
      non-root user (Atlas's build user, created via `useradd`).
    - `-c`: clean the working copy first (a fresh, reproducible build env).
    - `-n`: run `namcap` on the result.
    - `-I <pkg>`: install a local package into the copy before building — how we inject
      already-built AUR dependencies (v1 dep model; no LocalRepo to manage). Repo deps are
      resolved inside the chroot from the mirrors automatically.
    - makepkg args after `--` are forwarded to the inner `makepkg`. Note: do **not** pass
      `--nodeps` here (unlike the host build) — the chroot resolves deps itself (`--syncdeps`).
    """
    cmd = [MAKECHROOTPKG, '-r', chroot_dir]
    if makepkg_user:
        cmd += ['-U', makepkg_user]
    if clean:
        cmd.append('-c')
    if namcap:
        cmd.append('-n')
    for pkg in (inject_pkgs or ()):
        cmd += ['-I', pkg]
    extra = list(makepkg_args) if makepkg_args else []
    if extra:
        cmd.append('--')
        cmd += extra
    return cmd
