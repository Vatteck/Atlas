# Copy exact command (2026-06-05)

**Backlog item:** "Copy exact command — copy equivalent install/update/Flatpak-override/reflector
command. GUI stays primary, nothing feels hidden." (Power-user sugar)

## Why
Atlas's angle is "pretty enough for GUI people; honest enough for Arch people." A CLI user should be
able to see exactly what a GUI action maps to on the command line — no hidden magic.

## Increment 1 (this change) — transaction commands in the preview
The pre-flight transaction preview already gates install/update/uninstall and knows the action + the
package id. Add a **"⧉ Copy command"** button to its footer that copies the equivalent terminal
command for that exact transaction.

### Backend — `AtlasApi.get_command(pkg_id, action='install')`
Returns `{command, note}`, built from the real package object (accurate identifiers):
- **Official repo:** `sudo pacman -S <name>` (install/update) · `sudo pacman -Rns <name>` (uninstall)
- **AUR:** `git clone https://aur.archlinux.org/<package_base>.git && cd <base> && makepkg -si`
  (install/update; `note` adds the helper alternative `paru -S <name>`) · `sudo pacman -Rns <name>`
  (uninstall)
- **Flatpak:** `flatpak install flathub <app_id>` / `flatpak update <app_id>` /
  `flatpak uninstall <app_id>` (uses `pkg.id`, the real app id — not the display name)

`command` is `''` for actions with no clean one-liner (e.g. downgrade); the frontend then hides the
button. `shlex.quote`d; never raises.

### Frontend
- Footer button (`#tx-preview-copy-cmd-btn`, in a new `.modal-footer-left` group beside "View
  PKGBUILD"), shown for single-package install/update/uninstall (not the Update-All aggregate).
- `copyEquivalentCommand(pkgId, action, btn)` calls `get_command`, copies to the clipboard, flashes
  "✓ Copied", and toasts the command (+ note) so the user sees what they got.

### Tests
- `test_api.py::CommandTest` — repo/AUR/Flatpak × install/update/uninstall, helper note, empty for
  unsupported action, unknown-id error.

## Increment 2 (shipped 2026-06-05) — detail page + reflector copy
- **Detail-page "Copy command"** — a left-aligned button in the detail-modal footer (reads as a
  utility, not a commit button), shown for arch/aur/flatpak. Copies the command for the **primary
  action** (not-installed → install, installed+update → update, else uninstall), reusing
  `get_command` + `copyEquivalentCommand`. Browse-and-copy without committing.
- **Reflector copy in Mirrors** — Settings → Mirrors already *previewed* the regen command
  (`get_mirror_status().command`); added a **"Copy command"** button beside Regenerate that copies it
  (+ "✓ Copied" / toast). No backend change.

## Increment 3 (shipped 2026-06-06) — `flatpak override` command on the Permissions page
The deferred final surface. Rather than a button per toggle (huge surface), each permission **edit**
now surfaces the exact `flatpak override --user <flag> <app_id>` it ran:
- **Backend:** new pure `permissions.override_command(app_id, flag)` (shlex-quoted; `''` for an
  unknown flag / empty app id). The four `AtlasApi.set_flatpak_*` methods (`override` / `filesystem`
  / `bus` / `env`) now return `{'status':'ok','command': …}` on success, computed from the same pure
  `*_flag` helpers the gem applies (so the displayed command is exactly what ran). Failure → error,
  no `command`.
- **Frontend:** `showToast` gained an optional `copyText` (a copyable command — click the toast to
  copy, with a "⧉ Click to copy command" hint). A shared `permissionUpdatedToast(r)` shows
  `Updated · <command>` (copyable) when a command came back, else the old generic
  "effective next launch" toast. Wired into all four permission edit paths (the Permissions page
  toggle/filesystem/bus/env handlers + the detail-modal quick editor popup).
- **Tests:** `test_permissions.py::test_override_command`, `test_api.py::FlatpakOverrideCommandTest`
  (4 surfaces + failure has no command), `main_js_contracts::testPermissionUpdatedToastSurfacesCopyableCommand`.

**This completes the "Copy exact command" theme** — install/update/uninstall (preview + detail),
reflector (Mirrors), and now per-edit flatpak override (Permissions). **Needs a GUI eyeball** (toggle
a Flatpak permission → toast shows the override command → click to copy).
