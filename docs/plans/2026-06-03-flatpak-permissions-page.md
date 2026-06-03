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

1. **Page scaffold + static toggles** (Share / Socket / Device / Features). App picker + grouped
   switch cards with flag sub-labels. Backend: grouped spec (extend `permissions.EDITABLE` into
   `EDITABLE_GROUPS`), parse `features`/`persistent` in `parse_context`, `--allow/--disallow` in
   `override_flag`. The bulk of Flatseal's common toggles; pure logic stays unit-tested.
2. **Filesystem section**: predefined dir toggles + custom-path add/remove + ro/rw mode.
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
