# Plan — Transaction timeline + friendly failure summary

**Date:** 2026-06-05
**Status:** SHIPPED (frontend-only) — needs a GUI eyeball. 490 tests + 31 JS green.
**Backlog item:** "Transaction timeline polish" (BACKLOG → Operation confidence).

## Goal

The pre-flight **preview** (what *will* happen) just shipped. This is the other half: make the
**live + final** transaction view (the terminal panel) calm and legible instead of a raw log wall —
closing the operation-confidence loop. Four pieces:

1. **Step timeline** — a vertical stepper of the high-level phases (resolve → download → build →
   install → post-checks) the gem reports, with done / active / failed states.
2. **Collapse/expand raw output** — the raw log stays available but can be folded; the timeline +
   status are the primary view.
3. **Copy full log** — one button to copy the entire raw log to the clipboard.
4. **Friendly failure summary** — on failure, a card at the top naming the likely cause (download
   404 / PGP-keyring / file conflict / missing dep / build error / auth) with a one-line next step.
   The raw log stays below.

## Design decisions

- **Timeline = the gem's own `change_status` sequence, not a fixed 5-step model.** Mapping arbitrary
  i18n status strings onto a hard-coded resolve/download/build/install list is fragile and lies when
  a gem does something else. Instead: each `change_status` marks the previous step done and starts a
  new active step. This *naturally* reads "Synchronizing → Checking deps → Downloading → Building →
  Installing" because that's what the gem actually reports — honest and gem-agnostic. `change_substatus`
  stays as the active step's detail line.
- **Friendly failure summary is a pure, testable parser** (`summarizeFailure(logText) -> {title,hint}|null`),
  matched against the accumulated raw log on failure. Ordered most-specific-first (auth → PGP →
  download → file conflict → dependency → build → generic fallback). Advisory; never hides the log.
- **No backend change.** The watcher already pushes `terminalSetStatus / SetSubstatus / Append /
  SetDone`; all of this is frontend. The log buffer is accumulated client-side from `terminalAppend`.
- Pure helpers (`summarizeFailure`, `buildStepsHTML`) live in the Node-VM contract harness.

## Frontend

- `index.html`: add `#terminal-steps` (stepper), `#terminal-failure` (summary card), a **Copy log**
  header button, and wrap `#terminal-output` with a **Raw output** collapse toggle.
- `main.js`:
  - `terminalOpen`: reset steps + the client log buffer + failure card; header status → "Working…".
  - `terminalSetStatus(msg)`: push a timeline step (prev → done, new → active); render the stepper.
    (No longer overwrites the header state.)
  - `terminalAppend(line)`: append to the DOM *and* the client log buffer (for copy + failure parse).
  - `terminalSetDone(success)`: mark the active step done/failed; on failure render
    `summarizeFailure(buffer)` into `#terminal-failure`; header → Success/Failed.
  - Copy-log button → clipboard (reuse the existing `copyText` fallback pattern, short toast).
  - Output toggle → collapse/expand `#terminal-output`.
- `style.css`: stepper (dot + connector, active spinner, done ✓ green, failed ✗ red), failure card
  (toned like the danger notice), collapse toggle, header actions.

## Tests

- `main_js_contracts`: `summarizeFailure` (each category + generic + empty→null) and `buildStepsHTML`
  (done/active/failed markup). DOM-bound flow (open→status→append→done) optionally smoke-tested.

## Out of scope

- Per-step timing/durations, a true pacman-hook phase model, log search. (Possible later.)
- History/rollback center (separate BACKLOG item).
