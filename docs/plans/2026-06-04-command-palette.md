# 2026-06-04 — Command palette (Ctrl+K)

From BACKLOG → Open work (GUI sugar). A keyboard-first launcher: one shortcut opens an
overlay with a filterable command list — jump to any page or run an action without reaching
for the mouse. Frontend-only; reuses the existing handlers.

## Trigger & behaviour

- **Ctrl+K** (and **Ctrl+P**) opens the palette; **Esc** closes; works from anywhere.
- Type to **filter** commands — **fuzzy subsequence** match on label + keywords (`fuzzyScore`
  rewards contiguous runs + word-start hits; label beats keyword), best match first. **↑/↓**
  move the selection, **Enter** runs it, click runs it. Re-opening resets the query/selection.
- Commands that have a global shortcut show it as `<kbd>` badges (Ctrl+H, Ctrl+I, Ctrl+U,
  Ctrl+A, Ctrl+D, Ctrl+Shift+U, Ctrl+E, `/`).
- The palette is a centered-near-top modal (its own `#command-palette`), above the page but
  below blocking dialogs — it just closes on Esc, doesn't fight the watcher modals.

## Commands (v1)

- **Navigate**: Dashboard / Browse / Installed / Updates / News / Disk / Activity /
  Permissions / Settings → `activateView(...)`.
- **Actions** (reuse existing handlers):
  - Update all — `updateAllBtn.click()`; **only listed when updates exist** (button not hidden).
  - Clean up orphans — `cleanupOrphansBtn.click()`; **only when orphans exist** (button not hidden).
  - Refresh — `refreshBtn.click()`.
  - Toggle grid / list view — `setViewMode(...)`.
  - Select multiple — `toggleSelectMode(true)`.
  - Regenerate mirror list — `regenerateMirrors()`.
  - Open pacdiff — `pyApiCall('launch_pacdiff')`.
  - Export package manifest — `exportPackages()`.
  - Focus search — `searchInput.focus()`.

Each command: `{ id, label, hint, keywords, run, available? }`. `available()` is an optional
predicate evaluated when the palette opens (used to drop Update-all / Clean-orphans when their
topbar buttons are hidden). Mirror/pacdiff stay listed and fail-open with a toast if the tool
is missing (matches their button behaviour elsewhere).

## Structure (testable)

- **Pure**: `buildCommandList()` returns the registry filtered by `available()`;
  `filterCommands(commands, query)` does the substring match (label + keywords). Both
  unit-tested in the Node VM harness — no DOM.
- **DOM**: `openCommandPalette()` / `closeCommandPalette()` / `renderCommandResults(query)` /
  keyboard nav. Wired into the global `keydown` handler; click + input listeners on the palette.

## Files

- `index.html`: `#command-palette` modal (backdrop + input + `#command-results`).
- `main.js`: registry + the functions above; Ctrl+K/Ctrl+P in the keydown handler; update the
  shortcuts-help toast to mention it.
- `style.css`: `.command-palette` overlay, input, result rows, `.cmd-selected` highlight.

## Tests

- `main_js_contracts.test.js`: `filterCommands` matches by label and by keyword, empty query
  returns all, no match returns `[]`; `buildCommandList` drops a command whose `available()` is
  false. (Keyboard/render is DOM-bound; covered by the eyeball.)

## Verification

`python -m pytest` + Node harness green; **needs a GUI eyeball** (overlay, filtering, ↑/↓/Enter,
running an action).
