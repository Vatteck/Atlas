# History / Activity completion (2026-06-16)

## Goal

Finish the remaining History/Activity polish from BACKLOG:

1. Show a small per-package activity/history panel in the detail modal so users can answer
   “what did Atlas do to this package recently?” without leaving the package page.
2. Cap Atlas's local JSONL activity log automatically so long-running installs do not let
   `~/.cache/atlaspm/activity.jsonl` grow forever.

## Design

- Reuse the existing `activity_log.py` JSONL store and Activity-page render helpers; do not parse
  live pacman logs for the detail modal.
- Add an API method that filters recent Atlas activity by the package name/type behind a `pkg_id`.
  It must fail open with an empty list so the detail modal never blocks.
- Keep the detail panel read-only and compact: newest-first entries, action, source, timestamp,
  error text for failures, and a link to jump to the full Activity page filtered by name.
- Cap on write inside `record_activity` while holding the existing activity log lock. Preserve the
  newest entries and tolerate malformed lines by dropping them during compaction. The cap should be
  configurable through constants, not settings UI.

## Verification

- Unit-test JSONL capping with a temporary log path.
- Unit-test API filtering for exact package names.
- Node-contract-test the detail activity HTML builder and escaping.
