# Dedicated Flatpak permissions page (Flatseal-grade) — 2026-06-03

Expand the in-modal 7-toggle editor into a full **Flatseal-style** permissions manager: a sidebar
page where you pick an installed Flatpak and edit its whole sandbox, grouped by category, each row
showing the human label + the raw `flag=value` sub-label + a switch (matching Flatseal's layout).

Reuses the existing override backend (`flatpak override --user`, `set_override`/`reset_overrides`,
`AtlasApi.{get,set,reset}_flatpak_override(s)`) — the work is a bigger permission spec, parsing more
`[Context]`/bus/env sections, and the page UI. The in-modal quick editor stays as fast access.

## Categories & toggles (verified flag names)

**Static toggles** (on/off switch each; sub-label = the flag):
- **Share** `--share/--unshare`: network, ipc
- **Socket** `--socket/--nosocket`: x11, wayland, fallback-x11, pulseaudio, session-bus, system-bus,
  ssh-auth, pcsc, cups, gpg-agent, inherit-wayland-socket
- **Device** `--device/--nodevice`: dri, input, usb, kvm, shm, all
- **Features** `--allow/--disallow`: devel, multiarch, bluetooth, canbus, per-app-dev-shm

**Dynamic lists** (add/remove rows, not just on/off):
- **Filesystems** `--filesystem=X[:ro]` / `--nofilesystem=X`: predefined toggles (host, host-os,
  host-etc, home, the `xdg-*` dirs) **plus** custom paths, each with an access mode (ro/rw/create).
- **Session/System bus** `--talk-name`/`--system-talk-name` (+ own/see): name lists.
- **Environment** `--env=VAR=VALUE`: key/value list.
- **Persistent** `--persist=PATH`: path list.

Read current state from `flatpak info --show-permissions`: `[Context]` (shared/sockets/devices/
filesystems/features/persistent), `[Session Bus Policy]`, `[System Bus Policy]`, `[Environment]`.

## Page UX

- New **sidebar nav item** "Permissions" (Flatpak-only; hidden if Flatpak disabled).
- Layout: a list/dropdown of **installed Flatpaks** → selected app's permissions in grouped sections
  (Share, Socket, Device, Features, Filesystem, Bus, Environment), each a card of rows with switches,
  matching the Flatseal screenshot (label + `flag=value` muted sub-label + toggle on the right).
- Per-app **Reset to defaults**. Changes apply immediately (`--user`, no root), effective next launch.

## Increments

1. ~~**Page scaffold + static toggles**~~ ✅ **Done (2026-06-03).** Sidebar "Permissions" page,
   **master/detail** (installed-Flatpak list ← reuses `get_installed` → grouped permissions), iOS-style
   switches, `flag=value` sub-labels, per-app Reset. Backend: generic `_CATEGORIES` + `GROUPS` spec +
   `grouped_toggles()`, `parse_context` now also reads `features`/`persistent`, `override_flag` is
   generic over `"<category>:<value>"` keys (`--allow/--disallow` for features). Modal quick-editor
   refactored onto the same scheme (kept). Decisions: master/detail, iOS switches, keep both editors.
   Tests: `test_permissions.py` (18). Live-verified grouped output (Discord). **Needs a GUI eyeball.**
2. ~~**Filesystem section**~~ ✅ **Done (2026-06-03).** Predefined dir toggles (host/host-os/host-etc/
   home + the `xdg-*` dirs) each with a per-row access mode (rw/ro/create), plus custom-path
   add/remove. Backend: `parse_context` now keeps `filesystems_raw` (mode-bearing tokens) alongside
   the stripped `filesystems`; `filesystem_state()` splits grants into presets vs custom;
   `filesystem_flag(name, enabled, mode)` → `--filesystem=X[:mode]` / `--nofilesystem=X`;
   `set_filesystem_permission`/`set_flatpak_filesystem` glue. **Fixed a real bug**: `show_permissions`
   built `flatpak info --show-permissions <app> --None` when `installation` was unset (webview path),
   so it returned nothing — the grouped page *and* in-modal editor were silently empty for many
   installed apps. Now appends branch/installation only when present. Tests: +6 (filesystem_state,
   filesystem_flag, filesystems_raw). Live-verified against Flatseal & Discord.
3. **Bus (talk/own) + Environment + Persist**: dynamic add/remove lists (parse the bus/env sections;
   `--talk-name`/`--no-talk-name`, `--env`, `--persist`).

## Open decisions (confirm before building #1)

- **Page layout:** master/detail (app list on the left, permissions on the right) vs an app dropdown
  atop a single scrolling panel? (Master/detail scales better for many apps.)
- Keep the in-modal quick 7-toggle editor, or replace it with a "Open in Permissions page" link once
  the page exists? (Lean: keep both — quick toggles in the modal, full control on the page.)
- Switch styling: add a reusable toggle-switch component (Flatseal uses iOS-style switches) vs the
  current checkboxes?

## Honest scope

This is effectively porting Flatseal — a multi-increment feature. The static toggles (#1) are
straightforward; the dynamic lists (#2/#3) are the real work. All `--user`, no root.
