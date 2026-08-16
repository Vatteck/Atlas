# GUI settings surface for upgrade holds

**Date:** 2026-08-16
**Status:** draft → implemented
**Type:** webview settings page (main.js) + AtlasApi settings block. No Rust, no Qt.

## Problem

The upgrade-pipeline safety work (plan 2026-08-16-upgrade-pipeline-safety.md, 0.16.2) added
hold support: `arch_config['ignored_packages']` is honored by the summarizer
(`updates.py::__filter_ignored_packages`) and passed to pacman as `--ignore=<pkg>` during
upgrades, and the vendored-conflict dialog can persist a hold on the fly. The plan explicitly
deferred the management surface: *"No GUI settings surface for holds yet — config file only;
UI follow-up later."* This is that follow-up.

## Solution

A **"Upgrade holds"** section on the Settings page (visible when the Arch gem is available):

- Lists the current holds (chips, `<code>` + remove button).
- Add box: text input + "Hold package" button (Enter works too). Client-side validation:
  non-empty, `[A-Za-z0-9@._+:-]+`, no duplicates.
- Removes are instant in the DOM; everything persists via the existing **Save changes**
  button, consistent with every other settings section.
- Empty list shows "No held packages."

Backend (`AtlasApi`, api.py):

- `get_app_settings()` → `arch.ignored_packages` (list, from `arch_man.configman`).
- `save_app_settings()` → `arch.ignored_packages` accepted; cleaned (trim, drop empties,
  dedupe, sort) and persisted to `aconf['ignored_packages']`. Only touched when the key is
  present in the payload, so existing arch saves are unaffected.

## Files changed

- `atlas/view/webview/api.py` — settings arch block (get + save).
- `atlas/view/webview/main.js` — holds section render + wiring + `saveSettings` collection.
- `atlas/view/webview/style.css` — `.settings-holds-list` / `.settings-hold` /
  `.settings-hold-add` (uses existing `--bg-surface` / `--border-color` tokens).
- `tests/view/webview/test_api.py` — AppSettingsTest: get includes holds; save persists a
  cleaned list; arch save without `ignored_packages` leaves holds untouched.
- `tests/view/webview/main_js_contracts.test.js` — render contract for the holds section.

## Non-goals

- No migration/merge with the legacy per-package pin file (`UPDATES_IGNORED_FILE`) — that's a
  separate, pre-existing surface (pin button on packages) and stays untouched.
- No existence check on held names — holds may target packages that aren't installed or not
  in the repos yet (same latitude as `IgnorePkg` in pacman.conf).
- No holds management from the package context menu (the pin surface already covers
  per-package ignore; the settings list is the config-level view).
- No i18n — the Settings page is English by convention (existing sections are too).
- No GUI verification in this pass — needs a live session; unit + contract tests only.

## Verification

- `venv/bin/python -m pytest` green (777 + 3 new = 780).
- `node --test tests/view/webview/main_js_contracts.test.js` green (60 + 1 new contract).
- Manual (later, on a real box): add `bazaar` via the Settings add box → `Update all` skips
  it (`--ignore=bazaar` in the command preview / cannot_upgrade reason "Held (ignored
  upgrade)") → remove the hold in Settings → it's proposed again.
