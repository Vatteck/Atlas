# Webview Settings page (focused) — design

**Date:** 2026-06-01
**Status:** implemented
**Type:** Python (AtlasApi) + webview front-end. No Rust, no Qt.

## Problem

The Settings nav was a placeholder ("not yet implemented in Web UI") and there were no
settings API methods. After we disabled Snap/Debian/Web by default (2026-06-01), the
intended way to re-enable a package type didn't exist — a real gap created by that change.

The pre-existing backend settings builder (`GenericSettingsManager.get_settings`) is
Qt-era: it **imports PyQt5** and includes Qt-only options (widget style, HDPI) that do
nothing in pywebview. Rendering that whole tree would re-entrench the Qt dependency and
surface irrelevant options.

## Decision

A **focused, webview-native** Settings page that talks **directly to the config managers**,
not the Qt settings tree. Covers what matters for an Arch webview app:

- **Package types** — enable/disable each gem (the headline; fixes the re-enable gap).
- **Flatpak install level** — system / user / ask.
- **General toggles** — suggestions, system notifications, ask-to-reboot, download icons,
  remember root password.

## Backend (`AtlasApi`)

- `get_app_settings()` → `{types:[{id,label,enabled,can_work}], flatpak_available,
  flatpak_installation_level, general:{...}}`, read from `manager.configman` and each
  manager's `is_enabled()`/`can_work()`. A type that can't work on this system is reported
  `can_work:false` (rendered disabled).
- `save_app_settings(payload)` →
  - enabled types → `core_config['gems']` (list of gem dir names) **and** `set_enabled()`
    on the live managers, so the change applies without a restart (`_can_work` gates every
    op on `is_enabled()`; lazy `_ensure_prepared` handles a newly-enabled gem on next use).
  - general toggles → core config; Flatpak level → the flatpak gem's config (validated to
    system/user/None).
  - persists via each `configman.save_config(...)`.

## Front-end

`renderSettings()` replaces the placeholder: sections for Package types (checkboxes,
disabled+noted when `!can_work`), Flatpak (level select, only if available), General
(toggles), and a Save button. `saveSettings()` collects the controls, calls
`save_app_settings`, clears `packageCache` (type changes alter results), and toasts.

## Out of scope

- The full Qt settings tree (advanced/backup/tray/per-gem tabs, Qt styles). Add specific
  per-gem options here à la carte if a need arises, rather than rendering the Qt tree.
- Removing the residual PyQt5 coupling (separate known-gap item in STATUS.md); this page
  simply doesn't use it.

## Tests

`tests/view/webview/test_api.py::AppSettingsTest` — payload shape, gems list written +
live `set_enabled`, general toggle persisted, invalid Flatpak level → ask.
