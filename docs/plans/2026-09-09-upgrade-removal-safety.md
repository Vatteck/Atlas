# Upgrade removal safety — Atlas removed the running kernel

**Date:** 2026-09-09
**Status:** design; root cause investigated, not yet implemented
**Severity:** highest. A routine Update All left the machine with no kernel package and no
`mkinitcpio`, then the CachyOS hook advised a reboot.
**Branch:** `fix/upgrade-removal-safety` (off `origin/master` @ `6a84ab1`)

---

## What happened

On 2026-09-09, Update All on the maintainer's CachyOS machine ran this **twice** (10:22:03
and 11:35:25), with no confirmation prompt:

```
pacman -R --noconfirm cachyos-gaming-meta linux-cachyos-headers winetricks mkinitcpio
  linux-cachyos-nvidia-open cachyos-gaming-applications wine ntsync-autoload protontricks
  linux-cachyos limine-mkinitcpio-hook
```

Afterwards `pacman -Q linux-cachyos mkinitcpio` reports both missing. The running kernel
(`7.1.8-1-cachyos`) survived only because it was already loaded. `cachyos-reboot-required.hook`
then printed "Reboot is recommended" — a reboot at that point risked an unbootable system.

Evidence: `/var/log/pacman.log` (the `pacman -R` lines above),
`~/.cache/atlaspm/logs/atlas.log`, and `pacman -Q`.

## Root cause

### The defect: a declared conflict on a *virtual* name is expanded to every provider

[`updates.py` `_map_conflicts`](../../atlas/gems/arch/updates.py) reads each package's declared
conflicts (`data['c']`, the `Conflicts With` field). For each conflict name it does:

```python
conflict_providers = providers.get(conflict_name)
if conflict_providers:              # the conflict name matches a provided package
    if len(name_op_exp) == 1:       # no version expression
        checked_conflicts.update((p for p in conflict_providers if p != pkg_name))
```

Every provider of that name (except the declaring package itself) becomes a conflict.
`_fill_conflicts` then writes each one into `context.to_remove`, and `_upgrade_repo_pkgs`
removes them.

**Why that is wrong.** Arch's standard idiom for mutually-exclusive alternatives is for a
package to both *provide* and *conflict with* the same virtual name. Confirmed on this machine:

```
Name            : limine-mkinitcpio-hook
Provides        : limine-entry-tool
Conflicts With  : limine-entry-tool
```

The declaration means "only one package may fill this role at a time." pacman resolves that
as a *replacement* during a transaction. Atlas resolves it as *delete all the other providers*.

CachyOS makes this maximally dangerous, because it ships a dozen kernels sharing virtual names:

```
linux-cachyos       :: KSMBD-MODULE  NTSYNC-MODULE  VHBA-MODULE  WIREGUARD-MODULE  …
linux-cachyos-bmq   :: KSMBD-MODULE  NTSYNC-MODULE  VHBA-MODULE  WIREGUARD-MODULE  …
linux-cachyos-bore  :: …  (and nine more)
```

`mkinitcpio` and `dracut` likewise both `Provides: initramfs`, and **neither declares a
conflict with the other** — so any third package conflicting on `initramfs` sweeps in whichever
one the user has.

### Two failures let it reach the disk

1. **No confirmation.** [`_remove_transaction_packages`](../../atlas/gems/arch/controller.py)
   removes without asking. A `_confirm_removal` dialog exists in the same file but is wired
   only to the manual uninstall action, never to the upgrade path.
2. **The guard structurally cannot catch this.** The only check is reverse-dependency based —
   "never remove a package that installed packages still require." A kernel is a **leaf**:
   nothing depends on `linux-cachyos`, so `unprotected` is empty and the fail-closed check
   passes. The same is true of `mkinitcpio` and `limine-mkinitcpio-hook`. The guard protects
   exactly the packages that don't need protecting.

### Not the cause: the stale database

A second, independent bug was found in the same session: `pacman -Syy` ran at 10:19:22 but
`/var/lib/pacman/sync/*.db` are still dated 2026-09-04, while Atlas wrote its `db_sync` marker
anyway — so `should_sync()` returned "already synchronized" for the rest of the day. Update
*detection* uses `checkupdates` (which syncs its own temp DB and correctly saw 115 newer
versions); *execution* uses `pacman -S <names>` with no `-y`, resolving against the stale local
DB where the installed versions are newest. Result: pacman logged `reinstalled` for all 115
packages and Atlas reported success while nothing was upgraded.

**That bug did not remove the kernel.** It gets its own plan — see Follow-ups.

## Still to pin down

The expansion mechanism is confirmed from the code and the package metadata. **The specific
declaring package whose conflict expanded to `linux-cachyos` is not yet identified.**
`linux-cachyos` itself declares `Conflicts With: None`, so some other package in the
transaction declared a conflict on a name that `linux-cachyos` provides.

Phase 2 must not begin until that exact chain is reproduced. Phase 1 does not depend on it.

## Design

### Phase 1 — safety (lands first, independent of the conflict logic)

Strangler-fig per AGENTS.md §3.3: put a guard in front of the existing behaviour before
changing it.

**1a. Protected packages.** A package that provides the running system's ability to boot is
never removable as a side effect of an upgrade. Refuse and abort the removal, surfacing why.

The set must be derived, not hardcoded to one distro:
- the package owning the running kernel (`uname -r` → `/usr/lib/modules/<release>` → `pacman -Qo`)
- any package providing `initramfs`
- the packages owning files in `/boot`
- explicit names as a backstop: `linux*`, `mkinitcpio`, `dracut`, `grub`, `systemd-boot`, `limine`, `refind`

Hardcoding a CachyOS list would be wrong; deriving from the live system is both safer and
distro-agnostic. A hardcoded backstop is acceptable *in addition*.

**1b. Confirm every upgrade-path removal.** Reuse the existing `_confirm_removal` dialog.
It must name every package to be removed and the reason recorded on each `UpgradeRequirement`
("Conflicts with 'X'"), and default to cancelling. Per the project's UI convention
(memory: warnings calm, not scary), this is a plain, factual list — the safety comes from the
affordance, not from alarming prose.

An Update All that silently deletes packages is the actual defect here; even with Phase 2
correct, removals during an upgrade deserve consent.

### Phase 2 — correctness (only after the reproduction exists)

Stop treating "declares a conflict on a virtual name" as "remove every provider."

Rules to encode:
- A package that both **provides** and **conflicts with** the same name is declaring
  mutual exclusion for a *role*. The correct resolution is replacement — which pacman performs
  itself — not removal by Atlas.
- Expanding a conflict to all providers is only defensible when the conflict names a **real**
  package, not a virtual one. `_map_virtual_providers` already distinguishes these; the
  `len(name_op_exp) == 1` branch ignores that distinction.
- When in doubt, prefer letting pacman resolve the transaction and reporting the failure, over
  Atlas pre-emptively deleting packages. Atlas is a front-end; pacman is the resolver.

## Testing

Phase 1 and Phase 2 are both pure-logic changes over data structures already built by the
planner, so both are unit-testable without touching a real system.

TDD, per AGENTS.md. Minimum cases:

**Phase 1**
- The package owning the running kernel is refused, with the transaction aborted.
- A package providing `initramfs` is refused.
- An ordinary leaf package is *not* refused (the guard must not block legitimate removals).
- The confirmation lists every package and reason, and cancelling aborts the upgrade.

**Phase 2**
- A package declaring `Conflicts: X` where it also `Provides: X` does **not** schedule other
  providers of X for removal. Use the real `limine-mkinitcpio-hook` shape.
- A package declaring `Conflicts: <real package>` still schedules that package (no regression).
- Twelve kernels providing `KSMBD-MODULE` produce no removals when one is upgraded.

**Regression fixture:** build the real removal set from this incident — the eleven package
names, with CachyOS's actual provides/conflicts metadata — and assert it comes back empty.

## Verification

Unit tests cannot prove the end-to-end behaviour, and this is the one bug where "it looked
fine" is not good enough. Required before this is called done:

1. **In a disposable Arch/CachyOS container, never on the host.** Run Update All against a
   system with multiple kernel variants available and confirm no removal is proposed.
2. If any removal *is* proposed, confirm the dialog appears, names the packages, and that
   cancelling aborts cleanly.
3. `pacman -Q linux-cachyos mkinitcpio` still resolves afterwards.

This is exactly the case for the distrobox sandbox discussed on 2026-09-09 — a container makes
a wrong argv or a wrong removal set cost nothing.

## Follow-ups (separate plans)

1. **Stale-database / reinstall-instead-of-upgrade.** Detection and execution read different
   database views. Needs its own investigation: why `pacman -Syy` returned success without
   refreshing the DBs, and whether execution should pass `-y` or share checkupdates' view.
2. **Timing logs span human wait.** `_fill_to_install` logged "105.49 seconds" of which ~103
   was the user answering a providers dialog. A future agent measuring performance will chase
   a ghost.
3. **Coordination.** `fix/upgrade-removal-safety` touches `updates.py` and `controller.py`.
   The `claude/amazing-yalow-a5930c` shell-free branch rewrites neighbouring code in
   `controller.py` and `pacman.py` (including `upgrade_several`). Decide a merge order before
   either lands. PR #7 (search normalization) is unrelated and parked.
