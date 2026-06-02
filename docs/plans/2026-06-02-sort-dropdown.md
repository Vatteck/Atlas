# Sort dropdown

**Date:** 2026-06-02
**Status:** shipped (backend + frontend + test; awaiting a GUI eyeball)
**Backlog item:** "Sort dropdown" (docs/BACKLOG.md → Lighter QoL)

## Goal

A topbar **Sort** dropdown next to the type filter / view toggle: order the package list by
votes, popularity, recently-updated, or name — on top of the existing relevance ranking.

## Sortable data (what the serialized pkg already carries)

`_serialize_pkg` exposes `votes` and `popularity` (AUR metadata; `None` for non-AUR). The
Arch gem also populates `last_modified` (epoch int, from the AUR RPC via `mapper`), but that
field isn't serialized yet — add it. Repo/Flatpak/AppImage packages have no votes/popularity/
last_modified, so under those sorts they fall to the bottom (missing → sorts last).

## Modes

- **Relevance** (default) — unchanged: `sortByRelevance` for a search query, else `rankAur`.
- **Votes** — `votes` desc.
- **Popularity** — `popularity` desc.
- **Recently updated** — `last_modified` desc (AUR-populated).
- **Name (A–Z)** — `name` via `localeCompare`.

For the explicit modes the dropdown wins over search relevance (if you pick Votes mid-search,
you get votes order). Missing numeric values sort last; ties break on original index (stable).

## Implementation

- **Backend:** add `'last_modified': getattr(pkg, 'last_modified', None)` to
  `_serialize_pkg` (`atlas/view/webview/api.py`). One line; test asserts it's present.
- **Frontend (`main.js`):**
  - `sortMode` state persisted to `localStorage['atlas_sort_mode']` (validated against the
    allowed set; defaults to `relevance`).
  - `sortPackages(list, query)` dispatches on `sortMode` (relevance keeps today's behaviour).
  - `renderFiltered()` calls `sortPackages(...)`; `renderCategoryPackages()` sorts its fetched
    list the same way (so Browse respects the choice at open time).
  - `#sort-filter` change → persist + re-render the current package view (`renderFiltered`).
    Live re-sort covers dashboard/installed/updates/search; Browse applies on category (re)open.
- **`index.html`:** `<select id="sort-filter" class="styled-select">` in `.filters`, between
  the type filter and the view toggle. Reuses existing select styling.

## Out of scope

- Live re-sort of an already-open Browse category on dropdown change (would need to cache the
  open category's packages to avoid a refetch) — reopening the category applies the new sort.
- Per-source sort semantics beyond "missing sorts last".
