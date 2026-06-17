# Theme 5: Package queue across views

**Date:** 2026-06-16
**Status:** Plan (not started) — dedicated plan for competitive-research Theme 5 (Pacsea's persistent
queue). Parent: [2026-06-16-competitive-research-improvements.md](2026-06-16-competitive-research-improvements.md).

## Goal

Let the user **collect packages while browsing/searching across views**, then review and install the
whole set in one place — instead of today's per-view Select mode that resets when you navigate away.

## What exists today (grounded)

- `selectMode` (bool) + `selectedPackages` (Set of pkg ids), toggled by `#select-mode-btn`
  (`toggleSelectMode`), which **clears the selection** each time and only decorates `.package-card`s
  currently in the DOM.
- `updateBatchBar()` resolves selected ids against **`currentPackages`** (the *current view's* list),
  and `#batch-bar` shows Install/Uninstall-Selected. Install routes through `batch_install(ids)`
  (backend); uninstall through `batch_uninstall`.
- **The gap:** selection is keyed by id but only meaningful within `currentPackages`. Changing view
  rebuilds `currentPackages` (and `setActiveView`/search clears state), so a cross-view selection
  loses the package metadata and the batch bar can't resolve it.

## Design

### Frontend state (the core change)
- A persistent **`installQueue`**: an array of *minimal pkg snapshots* — `{id, name, type, icon_url,
  version, installed}` — captured at add-time so the queue survives view changes (no dependence on
  `currentPackages`). Backed by `localStorage` (`atlas_install_queue`), loaded on boot.
- Helpers (pure where possible, for contract tests): `queueAdd(pkg)`, `queueRemove(id)`,
  `queueHas(id)`, `queueClear()`, `buildQueueReviewHTML(items)` (the review-modal list).

### Entry points
- An **"Add to queue" / "Queued ✓"** affordance on package cards (and the detail modal action row),
  alongside Install. Toggles membership; updates the card state + the queue badge. Only for
  **not-installed** packages (installing already-installed is a no-op; uninstall stays out of the
  queue for v1 — install-only, matches Pacsea's "to install" basket and keeps the mental model clean).
- Keep the existing per-view Select mode as-is (it's still useful for one-off multi-select within a
  view); the queue is the *cross-view* persistent layer. They can share the `batch_install` backend.

### Queue badge + review
- A **"Queue (N)"** indicator (topbar or sidebar) visible when N>0; clicking opens a **review modal**:
  the list of queued items (icon + name + source chip + Remove), a **Clear** action, and an
  **Install all** button.
- **Install all** routes the queued ids through the existing **`batch_install(ids)`** so we reuse the
  proven path (and its progress/terminal handling). On success, clear the queue.

### Open question — aggregate preview vs per-item (decide before building)
Update-All uses one **aggregate** transaction preview. The queue can be mixed-source (repo + AUR +
Flatpak), which is harder to assemble into one preview. **Recommendation:** for v1, send the queue
through `batch_install` (which already sequences installs) and show the existing per-install
confirmation/preview each surfaces — *don't* build a new aggregate preview yet. Revisit an aggregate
"queue preview" (like Update-All's) as a follow-up once the basket UX is validated.

### Tests
- Contract: `queueAdd/Remove/Has` (dedupe by id, persistence round-trip via the localStorage stub),
  `buildQueueReviewHTML` (rows + escaping + empty state), badge count reflects queue size.
- The install path reuses `batch_install` (already covered) — assert the review modal calls it with
  the queued ids.

## Non-goals (v1)
- No uninstall queue (install-only basket).
- No new aggregate transaction preview (reuse `batch_install`); revisit later.
- No reordering/persistence-across-machines; localStorage on this box is enough.
- No dependency de-duplication across queued packages (the backend resolves per install).

## Effort / risk
Medium–large (new persistent UI surface + badge + modal), low backend risk (reuses `batch_install`).
The main design risk is UX scope creep — keep v1 to *add → review → install all*.
