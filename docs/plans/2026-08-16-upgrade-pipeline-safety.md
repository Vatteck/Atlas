# Plan: Upgrade-pipeline safety — walk the user through bazaar-class problems

Date: 2026-08-16
Status: Implemented
Version target: 0.16.2 (see STATUS.md)

## Problem (the 2026-08-16 incident, verified)

Atlas's scripted system upgrade removed `qemu-full` + `qemu-block-gluster` with
`pacman -R --noconfirm -dd` and then failed on the bazaar 0.9.4-1 file conflict
(`bazaar: /usr/include/libdex-1/dex-aio.h exists in filesystem (owned by libdex)`),
leaving the system un-upgraded until a manual `pacman -Syu --ignore bazaar`.

Root causes, each verified against live metadata and `/var/log/pacman.log`:

1. **`controller.py:1126` hardcodes `skip_checks=True`** for every transaction
   removal → `pacman -R -dd` unconditionally. The qemu removals were leaves
   (`Required By: None` — proven by the later clean `-Syu`), so `-dd` was
   unnecessary; if they had had dependents, the graph would have been broken.
   The removal plan itself was *correct*: qemu-common 11.1.0-1 declares
   `Conflicts With: qemu-system-cris qemu-system-nios2 qemu-block-gluster`.
2. **`updates.py` mutual-conflict handling strands legitimate upgrades.** The
   one-way conflict loop (`qemu-desktop` 10.1.0-1's `conflicts=qemu-full`,
   old packaging) correctly schedules `qemu-full` for removal, but
   `_handle_mutual_conflicts` drops *both* sides of any mutual pair into
   `cannot_upgrade` even when one side is already resolved by removal.
   Result: the 11.1.0 split family got dropped from the install set.
3. **No hold/`--ignore` support.** bazaar-class broken-repo-build conflicts
   (vendored files owned by another installed package) can only be escaped by
   cancelling the whole upgrade or by `--overwrite=*`, which corrupts the
   owning package. The correct answer is: hold the broken package, upgrade
   everything else, unhold later.

## Changes

1. **Kill the unconditional `-R -dd`** (`controller.py::_remove_transaction_packages`):
   - Validate removal targets against live reverse dependencies
     (`pacman.map_required_by`) minus the transaction's own removal set and the
     packages the `-S` step will replace/upgrade.
   - Unprotected dependents → refuse with a clear message, abort the upgrade
     (fail-closed). The planner's own cascade (updates.py:596-676) already
     sweeps dependents into `to_remove`, so a legitimate plan still succeeds.
   - Call `pacman.remove_several(..., skip_checks=False)` → plain `-R`.
   - New caller param `covered` = the to-upgrade set (dependents that the
     transaction itself replaces).
2. **Don't strand upgrades on removal-resolved conflicts** (`updates.py`):
   - Run the conflicts→`to_remove` loop *before* mutual handling, and skip
     mutual handling for pairs where one side is already scheduled for removal
     (the removal resolves the conflict; pacman does the same in-transaction).
3. **Hold support (`--ignore`)**, the bazaar walk-through:
   - New config default `ignored_packages: []` (persisted via existing
     configman; GUI-visible in the settings file).
   - `pacman.upgrade_several(..., ignored=...)` and
     `pacman.upgrade_system(..., ignored=...)` append `--ignore=<pkg>`.
   - `summarize()` moves held packages from `to_upgrade`/`to_install` into
     `cannot_upgrade` with reason "Held (ignored upgrade)" so the plan shows
     them honestly.
   - `_upgrade_repo_pkgs` filters held packages from the upgrade list at entry
     (log each skip) and passes `ignored` to the `-S` as belt-and-braces.
   - Conflicting-files branch: parse `pkg: file exists in filesystem (owned by X)`
     lines; when the owner is another installed package (vendored build,
     bazaar-class) offer **Hold package(s) and continue** — persist to
     `ignored_packages`, retry without them. Never auto-offer `--overwrite=*`
     for vendored conflicts. Non-vendored conflicts keep the existing
     overwrite dialog (files unowned by any installed package).
   - `upgrade_system` ("Quick system upgrade") passes held packages too.
4. **New i18n keys** in all 10 locale files:
   `arch.update_summary.held`, `arch.upgrade.error.conflicting_files.vendored`,
   `arch.upgrade.conflicting_files.hold`, `arch.upgrade.error.remove_refused`.
5. **Tests** (`tests/gems/arch/test_updates.py`): mutual-conflict pair where one
   side is already in `to_remove` stays upgradable; held packages surface in
   `cannot_upgrade`. Full 774-test suite must stay green.

## Non-goals

- No in-transaction `--ask` conflict resolution (pre-removal stays; refusals
  are honest aborts).
- No GUI settings surface for holds yet (config file is enough; UI follow-up).
- No scan-side filtering of held packages (they still show as upgradable;
  the plan and the executor skip them). Documented in STATUS.md.
- No change to the bazaar/libdex upstream issue itself (upstream packaging bug).

## Verification

- `python -m unittest` (774 tests) green.
- Manual: `pacman -S --noconfirm --ask=4 bazaar` dry check not needed —
  behavior verified via unit tests + the 16:47 incident replay reasoning in
  the plan review.
