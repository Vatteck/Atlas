# Sandboxed AUR builds — clean-chroot building ("Vault") — 2026-06-02

> **Status: IN PROGRESS (signed off 2026-06-03 — "start layer 3").** Supersedes the one-line
> "Container sandboxing (Vault) — aspirational" entry in BACKLOG.md.
>
> **Decisions locked at sign-off:** off by default (`aur_build_chroot`, host build stays the proven
> path); v1 dep model = **`-I` injection** (no LocalRepo); default chroot dir =
> `/var/lib/atlas/aurchroot` (configurable); graceful fallback to the host build whenever devtools
> is absent or chroot setup fails.
>
> **Increments:**
> 1. ✅ **Engine (2026-06-03):** pure `chroot.py` — `available()`/`missing_tools()` precondition
>    checks + argv construction (`create_root_cmd`/`update_root_cmd`/`build_cmd`, incl. `-I`
>    injection). Fully unit-tested (`test_chroot.py`, 12). No wiring yet — commits to nothing.
> 2. ✅ **Config + lifecycle + wiring (2026-06-03):** `aur_build_chroot` / `aur_build_chroot_dir`
>    config (off; default dir `/var/lib/atlas/aurchroot`). `controller._build_in_chroot` creates the
>    chroot if absent (`mkarchroot`), else updates it (`arch-nspawn pacman -Syu`), then builds
>    (`makechrootpkg`) in the package dir; swapped into `_build` with a **host-build fallback**
>    (returns None → `makepkg.build`). Unit-tested (`test_chroot_build.py`, 5 + `test_chroot.py` 13).
>    **Privilege model VERIFIED from the devtools source** (not guessed — devtools was installed to
>    confirm): `check_root` (archroot.sh) no-ops when already root, else self-execs via sudo → so we
>    run mkarchroot/arch-nspawn/makechrootpkg **as root** (directly when the app is root; via
>    `sudo -S`+root_password otherwise). makechrootpkg refuses to run makepkg as root (line 382), so
>    we pass **`-U <build_user>`** in the root path (`atlas-aur`, created by `add_package_builder_user`);
>    the unprivileged path relies on the `SUDO_USER` our `sudo -S` sets. Copy-dir "root" collision is
>    self-guarded (line 45); default makepkg args already include `--skipinteg`/`--syncdeps`, so we
>    pass no extra makepkg args. **VERIFIED LIVE (2026-06-03):** built `yay-bin` in a fresh chroot
>    end-to-end — products landed in the package dir owned by the build user (so Atlas's
>    `__fill_aur_output_files` + pacman install work unchanged) and deps resolved inside the chroot
>    (`--syncdeps`). **Live-test bug fixed:** `mkarchroot` canonicalises `<dir>/root` with
>    `readlink -f`, which yields nothing unless the *parent* exists → `_build_in_chroot` now
>    `mkdir -p`s the chroot dir before `mkarchroot`.
> 3. ⏳ `-I` injection wired for AUR dep chains; reconcile Atlas's own host-side dep install
>    (`_handle_aur_package_deps_and_keys`) which is redundant/wrong in chroot mode (chroot
>    `--syncdeps` resolves repo deps itself).
> 4. ⏳ Settings UI toggle + makepkg.conf reconciliation (custom conf already passed to `mkarchroot -M`
>    on create; verify it's honored per-build).

## Goal

Optionally build AUR packages in a **clean chroot** (via Arch's `devtools` / `makechrootpkg`)
instead of directly on the host, matching what `paru` and `aurutils` do.

## Honest threat model — what this does and does NOT do

**Does:**
- Isolates the **build** (`prepare()/build()/package()` run in an nspawn chroot, not against your
  live `$HOME`/system) — a malicious or buggy build script can't scribble on the host.
- Enforces **dependency correctness** — builds in a minimal env, catching PKGBUILDs that rely on
  something already on your host (the original purpose of clean-chroot building).

**Does NOT:**
- Protect against a malicious **package**: the built `.pkg.tar.zst` is still installed on the host
  with pacman, and its `.install` scriptlets run **as root**. (This is the npm-axios-style threat —
  a compromised maintainer ships a bad release; sandboxing the build doesn't stop you installing it.)
- Fully prevent build-time network exfiltration: `makepkg` fetches sources over the network inside
  the chroot, so the build isn't network-isolated by default.

So the accurate framing is **"clean, isolated AUR builds like paru/aurutils,"** paired with the
**PKGBUILD review** Atlas already supports (`edit_aur_pkgbuild`, mark/unmark-PKGBUILD) — *not*
"immune to supply-chain attacks." Don't market it as the latter.

## Prior art (verified 2026-06-02)

- **paru** (`paru.conf(5)`): a `Chroot [= dir]` option that builds via **`makechrootpkg`**, plus
  `ChrootFlags` (passed to makechrootpkg) and `RootChrootPkgs` (chroot base, default `base-devel`).
  Notably **`Chroot` requires `LocalRepo`** — paru stages built packages in a local pacman repo so
  the chroot can resolve AUR deps from it. (Confirmed from paru's `paru.conf(5)`.)
- **Authoritative mechanics**: the `devtools` man pages, verified to exist and have content:
  `makechrootpkg(1)` — `makechrootpkg [OPTIONS] -r <chrootdir> [-- makepkg args]`, flags `-r`
  (chroot dir), `-c` (clean), `-u` (update working copy), `-I` (install/inject a package into the
  chroot before building), `-n` (namcap); plus `mkarchroot(1)` and `arch-nspawn(1)`. (The old wiki
  title "DeveloperWiki:Building in a clean chroot" appears to be **empty/moved** now — don't cite
  it; use the man pages, and note modern devtools also exposes a higher-level `pkgctl build`.)
- **aurutils**: clean-chroot building is its core workflow (`aur build` → `makechrootpkg` + a local repo).
- **Arch official packaging**: `devtools` (`mkarchroot`, `makechrootpkg`, `arch-nspawn`) is the
  standard; `extra-x86_64-build` is just a wrapper.
- **yay**: does *not* chroot by default — so this would be a differentiator.

## How Atlas builds AUR today (the thing we'd change)

Atlas owns its AUR pipeline (no yay/paru):
1. Fetch package (git/snapshot), optional PKGBUILD review/edit.
2. Parse `.SRCINFO`, resolve the dep tree itself (`dependencies.py`, `aur.py`).
3. **Build on the host**: `makepkg.build()` runs `makepkg -ALcsmf --skipchecksums --nodeps` via
   `SimpleProcess(cwd=pkgdir, custom_user=<pkgbuilder_user>)` (`atlas/gems/arch/makepkg.py:39`).
   `--nodeps` because Atlas installs deps itself; build runs as a dedicated unprivileged user.
4. Install the built `.pkg.tar.zst` with pacman (root).

Only **step 3** changes. Steps 1–2 (review + our own resolver/ordering) and 4 (pacman install) stay.

## Proposed design (strangler-fig)

1. **Config toggle** `aur_build_chroot` (bool, default **False**) in `ArchConfigManager`
   (alongside `aur_build_dir`, `aur_remove_build_dir`, `edit_aur_pkgbuild`). Off by default; the
   host build remains the proven path. Surface later in webview Settings.
2. **New build path** `makepkg.build_in_chroot(...)` (or a `chroot.py` helper) invoked from the
   controller's build step *only when the toggle is on*. Keep `makepkg.build()` untouched as the
   fallback. Prove the new path on real packages before considering a default flip.
3. **Chroot lifecycle** (needs `devtools`):
   - Create once: `mkarchroot <chrootdir>/root base-devel` (chrootdir under `aur_build_dir` or a
     dedicated `/var/lib/atlas/aurchroot`; configurable). ~hundreds of MB.
   - Update before a build: `arch-nspawn <chrootdir>/root pacman -Syu`.
   - Build: `makechrootpkg -c -r <chrootdir> [-I <built-dep>.pkg.tar.zst ...]` in the package dir.
4. **Dependency model.** Atlas already resolves + topologically orders the AUR dep tree and builds
   leaves first. For chroot builds, feed each already-built AUR dep into the dependent's build with
   `makechrootpkg -I <pkg>` (inject local packages). **v1 = `-I` injection** (no repo to manage);
   repo deps are installed inside the chroot from the configured mirrors automatically.
   *(paru instead requires a `LocalRepo`; that scales better for big dep sets but adds repo
   management — defer to v2 if `-I` injection proves clunky.)*
5. **Privileges.** `makechrootpkg` runs as a regular user and uses `sudo` for the nspawn parts, so
   run it as the `pkgbuilder_user` and route the sudo through Atlas's existing root-password broker.
6. **Preconditions / graceful degradation.** If `devtools` (`makechrootpkg`) isn't installed, or
   the toggle is on but chroot setup fails, **fall back to the host build** with a clear notice —
   never block an install because the chroot path is unavailable.
7. **Custom makepkg.conf.** The existing `_optimize_makepkg` path writes a custom `makepkg.conf`;
   in chroot mode that belongs *inside* the chroot (`arch-nspawn`/`-C`), not the host — reconcile.

## What this explicitly does NOT include (scope control)

- No network-isolated builds (sources need fetching); could be a later flag.
- No LocalRepo management in v1 (`-I` injection instead).
- No sandboxing of *running* installed apps (that was a different "Vault" interpretation — out).

## Testing

- **Unit**: assemble-the-argv tests (like `launch_pacdiff`) for `mkarchroot`/`arch-nspawn`/
  `makechrootpkg` command construction + the `-I` injection list. Mock the process layer.
- **Integration (manual, real Arch box)**: build a simple AUR pkg in-chroot; build one *with* an
  AUR dependency (exercises `-I` ordering); confirm fallback when `devtools` absent.

## Open questions for sign-off

- chroot location + disk budget (dedicated dir vs reuse `/var/lib/archbuild`)?
- `-I` injection vs a managed LocalRepo (paru's choice) for AUR dep chains?
- Is this worth the upkeep (chroot updates, devtools dep, root) for the realistic benefit, given it
  doesn't stop malicious *packages*? (Honest gut: nice-to-have, lower ROI than PKGBUILD-diff review.)
