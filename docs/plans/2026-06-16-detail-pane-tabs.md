# Detail pane: tabs + installed-files containment

**Date:** 2026-06-16
**Status:** ✅ shipped 2026-06-16 (needs a GUI eyeball). Suite 614 + JS 51 green.

> **Shipped:** `.modal-body` restructured into a `#detail-tabs` tablist + five `.detail-panel`s
> (Overview / Details / Dependencies / History / Build & Trust), existing section IDs preserved so
> every async render still works. Pure `computeDetailTabs(content, active)` decides tab visibility +
> active fallback (unit-tested); `updateDetailTabs(isAur)` applies it, called on open and after each
> async section settles. Installed files pulled out of the info table into a collapsible
> filterable/scrollable block via pure `buildInstalledFilesHTML(files)` (count header, filter input,
> 240px scroll list, render capped at 2000 rows with a note). Fixed a latent `--accent-primary` →
> `--accent-color` var typo in the AUR-comments CSS while here. Tests:
> `main_js_contracts::testBuildInstalledFilesHTML` + `testComputeDetailTabs`. **GUI eyeball:** tabs
> switch + auto-hide when empty; Build & Trust only for AUR; files filter narrows the list; big
> packages stay contained.
**Trigger:** GUI-eyeball feedback — (1) the "installed files" list in the detail pane balloons into a
giant wall of text; (2) the detail modal now has enough sections to warrant tabs.

## Problem

The detail modal `.modal-body` stacks ~10 sections vertically (badges, why-source, screenshots,
description, source-compare, Dependencies, Package history, Build recipe, AUR comments, Details
table, Version history). The Details table renders the arch `installed files` array (from
`pacman -Qlq`, often 1k–10k entries) as a single `val.join(', ')` cell — an unbounded wall of text.

## Decisions (from the user)

- **Tabs:** `Overview · Details · Dependencies · History` + a `Build & Trust` tab **for AUR only**.
  Empty tabs auto-hide.
  - **Overview:** rich badges, why-source, screenshots, description, source-compare, perms action.
  - **Details:** the info key/value table + a collapsible **Installed files** block.
  - **Dependencies:** the existing dependency summary section.
  - **History:** Package history (activity) + Version history.
  - **Build & Trust** (AUR): Build recipe (PKGBUILD) + AUR comments.
- **Installed files:** a collapsible block (`Installed files (N)`) containing a **filter input** and a
  **fixed-height scrollable list**.

## Design (pure-frontend — no backend change; the files data already arrives via `get_info`)

### index.html
Restructure `.modal-body` into a `#detail-tabs` tablist + five `.detail-panel[data-panel]`
containers. Move each existing section div (unchanged IDs) into its panel so every existing render
function keeps working by `getElementById`. Add `#detail-files-section` (hidden) in the Details panel.

### main.js
- **Tabs:** `activateDetailTab(name)` toggles `.active` on tab buttons + panels. `updateDetailTabs()`
  hides a tab whose panel has no visible (`:not(.hidden)`) content, force-shows Overview/Details,
  gates `Build & Trust` to AUR, and if the active tab gets hidden, falls back to the first visible
  tab. Reset to Overview on open. Call `updateDetailTabs()` synchronously at open and after each async
  section resolves (deps, activity, version history, comments, pkgbuild, info table) via
  `.finally(...)`.
- **Installed files:** in the `get_info` handler, intercept the row whose `prettifyInfoKey` label is
  `installed files` (covers `14_installed_files` and `installed files`) — don't add it to the table;
  instead render `#detail-files-section` from a pure `buildInstalledFilesHTML(files)` (header with
  count, filter input, scroll list; `''` for empty). Wire the filter to show/hide rows by substring
  (case-insensitive); show a "no match" line when filtered to zero. Render is capped (e.g. first 2000
  rows) with a note if exceeded, to bound DOM size for huge packages.

### CSS
`.detail-tabs` (sticky-ish tab bar, active underline), `.detail-panel`/`.detail-panel.active`
(show/hide), `.installed-files` collapsible + `.if-filter` input + `.if-list` fixed-height scroll.

### Tests (JS contracts — Node VM, pure builders)
- `buildInstalledFilesHTML`: count in header, rows escaped, `''` for empty, cap note past the limit.
- Tab behaviour: opening a non-AUR package hides `Build & Trust`; a package with no deps hides
  the Dependencies tab; the active tab falls back when hidden.

## Non-goals
- No backend change (files already provided; no new `pacman` call).
- No per-file actions (open/owns/which-package) — just list + filter for now.
- No virtualized list (a render cap is enough for the worst case).
