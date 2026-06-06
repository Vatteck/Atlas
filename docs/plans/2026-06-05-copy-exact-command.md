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

## Deferred to a later increment
- **Copy on the detail page** (browse-and-copy, without opening the install gate).
- **`flatpak override` command** on the Permissions page (copy the equivalent of a permission edit).
- **`reflector` command** — the Mirrors settings already *previews* the regen command; a copy button
  there would round it out.
