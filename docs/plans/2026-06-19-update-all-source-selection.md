# Update-All source selection

**Date:** 2026-06-19
**Status:** done (suite 710 + JS contracts green; needs a GUI eyeball)

## Problem

`Update All` upgrades every pending update across all sources in one shot. With the current
wave of malicious AUR uploads, the user wants to be able to *exclude AUR* (or any source)
from a bulk upgrade without having to update each package by hand — and have that choice
remembered between runs.

## Design

Source-level toggles in the existing Update-All transaction-preview modal (Arch / AUR /
Flatpak / AppImage). The choice is **remembered**: the set of *deselected* sources is
persisted, so unticking AUR once keeps it unticked next time. New/unknown sources always
default ON (we persist the skip list, not the keep list).

Source key = the serialized `type` (`arch_repo`, `aur`, `flatpak`, `appimage`), which is
exactly `pkg.get_type()` server-side — so frontend and backend agree without a mapping.

### Backend (`atlas/view/webview/api.py`)

- `update_all(self, exclude_sources=None)`:
  - reads installed, filters to upgradable (unchanged),
  - drops packages whose `get_type()` is in `exclude_sources`,
  - persists `exclude_sources` to `core['ui']['update_all_exclude_sources']`,
  - if nothing remains after filtering → friendly "nothing selected" return (no upgrade),
  - otherwise the existing get_upgrade_requirements + upgrade path (already routes a subset
    per-gem, verified in `view/core/controller.py:585`).
- `get_update_all_prefs(self)` → `{exclude: [...]}` — the remembered skip list, for
  pre-checking the toggles when the modal opens. Fails open to `{exclude: []}`.

### Frontend (`atlas/view/webview/main.js`)

- `buildUpdateAllPreviewData(updates, extras)`: add `data.sources = [{key,label,count}]`
  (only sources present, in trust order) and carry `extras.excluded` for the initial
  unchecked state.
- `buildTransactionPreviewHTML`: when `action === 'update-all'` and `data.sources`, render
  a "Sources to update" checkbox group (each `input[data-source][data-count]`), pre-checked
  unless its key is in the excluded set.
- `openTransactionPreview`: wire a change-listener on those checkboxes that recomputes the
  proceed-button label (`Update N`) and disables it when none are checked.
- Update-All click handler: fetch remembered prefs, build preview with them, and on proceed
  read the unchecked sources from the DOM and call `update_all(excluded)`.

### Persistence shape

`core['ui']['update_all_exclude_sources']`: `list[str]` of source keys to skip. `[]` =
update everything (today's behaviour).

## Out of scope

- Per-package selection (the user asked for *type*-level).
- Live recompute of the aggregate download size (button count only).

## Tests

- `buildUpdateAllPreviewData` emits the right `sources` list + counts (Node VM contract test).
- Backend: `update_all(exclude_sources=['aur'])` filters AUR out of the upgrade set and
  persists the skip list.
