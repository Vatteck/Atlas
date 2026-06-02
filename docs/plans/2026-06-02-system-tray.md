# System-tray indicator (non-Qt) — 2026-06-02

> **Status: phases 1 + 2 implemented + Settings UI (2026-06-02).**
> - Phase 1: `atlas/view/tray.py` (`AtlasTray` + `start()`) + `app.py` wiring +
>   `ui.tray.{enabled,minimize_to_tray}`. Menu (show/hide, updates, quit), opt-in close-to-tray.
> - Phase 2: update-count **badge** — a daemon-thread poller (`ui.tray.update_check_interval`
>   minutes, default 60, 0=off) calls `manager.read_installed()`, pushes the count to the GTK
>   thread via `GLib.idle_add` → `indicator.set_label(N)` + a "Updates available: N" menu item.
>   Label-only (no ATTENTION status — that needs a separate attention icon we don't ship).
> - Settings UI: a "System tray" section on the webview Settings page (enabled / close-to-tray /
>   interval), gated/greyed when the backend is absent. Tray changes apply on next launch.
> - Tests: `tests/view/test_tray.py` (20) + `test_api.py::AppSettingsTest` tray cases. Smoke-tested
>   on a real GTK loop (indicator builds; poller → badge flows). GUI-confirmed phase 1 on KDE;
>   phase 2 badge + Settings section still want a GUI eyeball.

## Goal

Reintroduce a system-tray presence for Atlas. The legacy **Qt** tray was purged during the
de-Qt'ing (see STATUS "Tray mode is gone"); this is a fresh, **pure-Python** implementation
that fits the pywebview/GTK stack and shows on modern desktops (KDE Plasma first-class).

## Backend decision

Use **AyatanaAppIndicator3** (`gi.repository.AyatanaAppIndicator3`, ver `0.1`), falling back
to the older **AppIndicator3** if only that typelib is present. Rationale:

- It emits a **StatusNotifierItem** (SNI) — the freedesktop tray protocol KDE Plasma supports
  natively (and GNOME via an extension). The deprecated `Gtk.StatusIcon` does **not** show on
  modern KDE/GNOME, so it's out.
- We already depend on **GTK3 + python-gobject**; the indicator lives on the *same* GTK main
  loop pywebview runs. No second toolkit, no Qt, no extra Python dep.
- Both typelibs are present on the dev box (verified). The only requirement is the system
  package `libayatana-appindicator` (provides the `AyatanaAppIndicator3-0.1` GIR typelib).

**Not** `pystray`: it would pull a separate abstraction and still bottom out on AppIndicator
on Linux — using the typelib directly is leaner and gives us label/badge control.

## Graceful degradation (golden rule: never break the app)

The tray is **additive and optional**. If neither typelib is importable (system package
absent), `tray.start()` logs at INFO and returns `None` — the app launches exactly as today.
Gated behind a config flag so it can be turned off even when available.

## Lifecycle / threading

`webview.start(gui='gtk')` owns the GTK main loop on the main thread. The indicator and its
`Gtk.Menu` must be created and mutated on **that** loop's thread.

- Build the indicator from `GLib.idle_add(...)` so construction runs on the GTK main thread.
  Kick it off from the `func` callback `webview.start(func=…)` runs after the GUI is up (that
  callback runs on a worker thread, hence the `idle_add` hop).
- Menu-item callbacks fire on the GTK main thread, so calling pywebview `window.show()/hide()/
  destroy()` from them is safe.
- Any background work (update polling, phase 2) marshals UI changes back via `GLib.idle_add`.

## Window integration

- Tray left-click / "Show Atlas" → `window.show()` + raise; "Hide" → `window.hide()`.
- **Close-to-tray (opt-in):** intercept the window `closing` event; if tray is active **and**
  `ui.tray.minimize_to_tray` is true, cancel the close and hide instead. Default **off** →
  closing quits exactly like today (tray is purely additive until the user opts in).
- **Quit** menu item: the only true exit when close-to-tray is on — `window.destroy()` ends
  the GTK loop, then the indicator is removed.

## Menu (phase 1)

```
Atlas
─────────────
Show / Hide Atlas      → toggle window visibility
Check for updates      → show window, navigate to the Updates view
─────────────
Quit Atlas             → destroy window (real exit)
```

Navigate-to-Updates reuses the existing JS router via
`window.evaluate_js("showSection('updates')")` (confirm the function/section id in `main.js`).

## Update badge (phase 2 — not in first cut)

Periodically reflect the update count on the indicator (`set_label("N")` / a distinct
"updates available" icon). The count comes from the same path the dashboard uses
(`AtlasApi.get_updates` → `manager.read_installed()` filtered on `p.update`). That call is
**heavyweight** (full installed read, may need a sync) so polling must be infrequent and
opt-in; deferred to keep phase 1 focused and measured. The existing `ui.tray.updates_icon`
config key is reserved for this.

## Config

Reuse the existing `ui.tray` block in `view/core/config.py` (currently
`{default_icon, updates_icon}` — bauh leftovers). Add:

- `ui.tray.enabled` (bool, default **True** when a backend is available)
- `ui.tray.minimize_to_tray` (bool, default **False**)

A Settings-page toggle (`get_app_settings`/`save_app_settings`) is a follow-up, not phase 1.

## Files

- **New:** `atlas/view/tray.py` — `class AtlasTray` (build indicator + menu, callbacks),
  `start(window, api, config, logger) -> Optional[AtlasTray]` factory with the import guard.
- **Edit:** `atlas/app.py` — after `api.set_window(window)`, wire the tray into
  `webview.start(func=…)`; add the `closing` handler for close-to-tray.
- **Edit:** `atlas/view/core/config.py` — the two new `ui.tray` keys.
- **Icon:** reuse `view/resources/img/logo.png` for the indicator.

## Legacy leftovers (decide, don't silently keep)

- `atlas/view/core/tray_client.py` (`notify_tray` writes a `notify_tray` cache file) — was IPC
  to a *separate* tray process. Our tray is **in-process**, so this is dead. Leave untouched in
  phase 1 (out of scope), flag for removal in a cleanup pass.
- `atlas/view/core/update.py`'s `tray=` param is **app self-update** checking, unrelated to the
  package tray — leave alone.

## Testing

- Pure-logic unit tests for the menu/state helpers (e.g. label formatting, the
  minimize-to-tray decision) — the GTK indicator itself can't be asserted headless.
- Manual GUI verification on KDE Plasma (Wayland + X11): icon appears, show/hide works,
  close-to-tray honors the flag, Quit exits. Mark **Needs a GUI eyeball** in STATUS.

## Risks / notes

- SNI on GNOME needs the AppIndicator extension; that's a desktop-side caveat, not our bug —
  note it in docs, don't work around it.
- Confirm pywebview's `window.events.closing` can **cancel** the close (return value / handler
  contract) before relying on it for close-to-tray; if it can't cancel, fall back to a plain
  "Hide" item and skip auto-hide-on-close.
```
