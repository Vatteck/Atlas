# Mirrorlist Regeneration Safety — 2026-07-16

## Problem

The "Regenerate mirror list" button in the .pacnew config-review center and Updates
notice runs `reflector` or `rate-mirrors arch`, both of which generate **upstream Arch**
mirrors. On Arch derivatives (CachyOS, EndeavourOS, etc.), this silently overwrites the
distro's custom mirrorlist with the Arch defaults — the user loses access to their
distro's package repos.

The code explicitly avoids `cachyos-rate-mirrors` (line 1611 comment: "NOT
cachyos-rate-mirrors — that targets the CachyOS mirrorlist, not this file"), but
`/etc/pacman.d/mirrorlist` IS the CachyOS mirrorlist file. The comment is wrong.

Additionally, there's no backup before regeneration, so the overwrite is irreversible
without manual intervention.

## Solution: A + D

**A)** Remove "Regenerate mirror list" from the pacnew center and Updates notice.
The pacnew center's job is config-file review (Discard / Apply / Diff / pacdiff), not
mirror management. Mirror regeneration belongs in Settings → Mirrors, where the user is
in "I am intentionally changing my mirrors" mode.

**D)** Add automatic backup before every regeneration + restore capability:
- Before regenerating, copy `/etc/pacman.d/mirrorlist` → `/etc/pacman.d/mirrorlist.atlas.bak`
- After regeneration, the Settings → Mirrors page shows a "Restore backup" button if
  a backup exists
- Restore copies the backup back (requires root)

## Changes

### api.py
1. New constant: `MIRRORLIST_BACKUP_PATH = '/etc/pacman.d/mirrorlist.atlas.bak'`
2. New method: `backup_mirrorlist()` — shutil.copy2 to the backup path
3. New method: `restore_mirrorlist_backup()` — root cp backup back to mirrorlist
4. New method: `get_mirrorlist_backup_status()` — checks if backup exists, returns age
5. Modify `regenerate_mirrorlist()` — call `backup_mirrorlist()` before running the tool

### main.js
1. `renderPacnewCenter()` — remove "Regenerate mirror list" button and its event listener
2. `renderUpdatesNotice()` — remove "Regenerate mirror list" button and its event listener
3. `regenerateMirrors()` — add confirmation dialog showing the command before running
4. `renderSettings()` — after mirror summary, check backup status and show restore button

### style.css
- Minor: `.mirror-backup` section styling (reuses existing `.settings-help` and `.btn-outline`)

## Non-changes

- `_mirror_regen_cmd()` is left as-is. The comment about cachyos-rate-mirrors is wrong
  but fixing it requires distro detection which is a separate feature. The backup + remove
  approach makes the tool choice less dangerous regardless.
- System Health → Mirrors action still calls `regenerateMirrors()` but now gets the
  confirmation dialog.
