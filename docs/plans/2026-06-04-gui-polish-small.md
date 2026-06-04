# 2026-06-04 — Small GUI-polish trio

Three frontend-only items from BACKLOG → Open work → GUI polish. One plan; ship together.

## 1. Density / layout modes

A display-density preference applied app-wide, persisted to `localStorage` (no backend).

- Modes: **Comfortable** (default), **Compact**, **Dense**.
- `setDensity(mode)` validates ∈ the three, writes `localStorage['atlas_density']`, and sets a
  `density-<mode>` class on `document.body` (removing the others). `applyDensity()` reads the
  stored value (default comfortable) and applies it; called on load.
- CSS: under `body.density-compact` / `body.density-dense`, tighten the package grid gap, card
  padding, list-row padding, and the attention/category gaps. Comfortable = current look (no class
  needed but we still set `density-comfortable` for clarity).
- Control: a **select in Settings → General** that **applies immediately** on change (it's a
  localStorage pref, independent of the Save button) + a help line saying so.
- `setDensity` / `densityValid` are pure-ish (DOM write only) — `densityClass(mode)` (mode →
  class, with fallback) is pure and unit-tested.

## 2. Contextual topbar

Show only the controls meaningful to the current context; hide the rest.

- The package-list controls — **type filter, sort, view-toggle, select** — are relevant only when
  the main grid is showing a package list: `installed` / `updates`, an **open Browse category**, or
  **any view with an active search**. Hidden on the dashboard (cards), Browse landing (categories),
  News, Disk, Activity, Permissions, Settings.
- `shouldShowPackageControls(view, hasQuery, inBrowseCategory)` — **pure**, unit-tested.
- `applyTopbarContext()` reads the live state and toggles `.hidden` on the four controls. Called
  from `activateView` (end), `fetchPackages` (after the query is known), `renderBrowse` (landing →
  off) and `renderCategoryPackages` (category → on).
- Search + refresh stay always visible (search is global; refresh re-runs the current view).
  Update-all / cleanup-orphans keep their own existing visibility logic.

## 3. Finish empty / error states

The states already exist but are inconsistent (plain text / `.news-empty` / inline styles). Unify
them with one helper and add an action where natural.

- `emptyStateHTML({icon, title, hint, actionLabel, actionView})` → a centered icon + title + hint
  (+ an optional button that `activateView(actionView)` on click via delegation). Pure; unit-tested.
- Apply to: **News** (load-fail / none), **Browse categories** (load-fail / none), **category
  packages** (none / load-fail), **Permissions** (no installed Flatpaks → action: Browse; perms
  unavailable), **Activity** (none). In-modal **screenshots/history** already hide when empty —
  left as-is (a hidden section is the right call there).
- Distinguish **offline/load-failure** (couldn't reach the source — retry guidance) from **genuinely
  empty** (nothing here yet) wording.

## Tests

`main_js_contracts.test.js`: `densityClass` (valid → class, junk → comfortable);
`shouldShowPackageControls` (installed/updates/search → true; dashboard/news/browse-landing →
false; browse-category → true); `emptyStateHTML` (renders title/hint, includes the action button
only when `actionLabel` given, escapes text).

## Verification

`python -m pytest` + Node harness green; **needs a GUI eyeball** (density switch, topbar hiding per
page, empty-state rendering).
