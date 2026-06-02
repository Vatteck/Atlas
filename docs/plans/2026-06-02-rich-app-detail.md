# Rich app detail page — screenshots + version history

**Date:** 2026-06-02
**Status:** done (2026-06-02)
**Scope:** enrich the existing package detail modal with **screenshots** (Flatpak/AppImage)
and a **version-history** table. Read-only; leans on backend that already existed in the
gem controllers but was never exposed to the webview.

## Why
The detail modal showed only the description + a key/value table. The orchestrator already
implements `get_screenshots` (Flatpak, AppImage) and `get_history` (all gems), but neither
was wired to `AtlasApi`. Surfacing them makes Atlas feel like a software store and pairs
with the README screenshots work.

## Backend (`atlas/view/webview/api.py`)
- `_serialize_pkg` now also emits `has_screenshots` (it already had `has_history`), so the
  frontend knows whether to fetch.
- `get_screenshots(pkg_id) -> {status, data:[url,...]}` — `list(manager.get_screenshots(pkg))`
  filtering falsy entries. Empty list is a valid `ok`.
- `get_history(pkg_id) -> {status, data:{history:[{...}], current_index:int}}` — wraps
  `manager.get_history(pkg)` (a `PackageHistory`: `.history` list + `.pkg_status_idx`).
  Run through `_json_safe` (history entries can carry datetimes).
- Both guard unknown ids and exceptions (matching `get_info`).

## Frontend (`index.html` / `main.js` / `style.css`)
- Detail modal gains `#detail-screenshots` (above the description) and a
  `#detail-history-section` (below the Details table), both hidden by default.
- `openDetailModal` fires `renderDetailScreenshots(pkg)` + `renderDetailHistory(pkg)`:
  - Screenshots: only if `pkg.has_screenshots`; render a horizontal thumbnail strip
    (lazy-loaded), each opening the full image via `open_url`; failed images self-hide.
  - History: only if `pkg.has_history`; build a table from the union of entry keys
    (prettified via the existing `prettifyInfoKey`), highlighting the installed version's
    row (`current_index`). Horizontally scrollable.
- Styles: `.detail-screenshots`/`.screenshot-thumb`, `.history-table`/`.history-current`.

## Tests (`tests/view/webview/test_api.py::RichDetailTest`)
- `get_screenshots` returns the URL list (filtering falsy) and errors on unknown id.
- `get_history` serializes entries (datetime → str) and reports `current_index`; errors on
  unknown id.

## Notes / follow-ups
- Arch repo packages have no screenshots (only Flatpak/AppImage via Flathub/AppImageHub) —
  the strip simply stays hidden for them; history still shows.
- GUI-verified working 2026-06-02.
- ✅ **Lightbox (2026-06-02):** clicking a thumbnail now opens a full-size in-app lightbox
  (`#screenshot-lightbox`) with prev/next + keyboard nav (Esc/←/→) and backdrop-to-close,
  instead of opening the image in the browser. `openLightbox()`/`wireLightbox()` in
  `main.js`, `.lightbox*` styles (z-index 400, above the modal at 300).
