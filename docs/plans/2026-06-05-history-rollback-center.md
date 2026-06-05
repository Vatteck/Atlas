# History / rollback center

**Status:** increment 1 shipped (2026-06-05) — needs a GUI eyeball; pacman-log links + log
management deferred to later increments.
**Backlog item:** "History / rollback center" (BACKLOG.md → Operation confidence) — *Wrap the
existing downgrade in a real History/Activity page: timeline of installs/updates/removals, filter
by package/source/action, a per-package History tab, "downgrade available" / "reinstall previous
version" affordances, pacman-log links.*

## What already exists (don't rebuild)

- **Activity log** (`atlas/view/webview/activity_log.py`): an append-only JSONL at
  `~/.cache/atlaspm/activity.jsonl`; `record_activity(action, pkg_name, pkg_type, success, error)`
  is called from every mutating `AtlasApi` handler (install/uninstall/update/downgrade/batch).
  `get_activity_log(limit=50)` returns newest-first. Entry shape:
  `{timestamp, action, pkg_name, pkg_type, success, error}`.
- **Activity page** (`renderActivityFeed` in `main.js`): a flat chronological list (icon + action
  chip + pkg + type + time + error). Reached via the sidebar (`activateView('activity')`,
  `Ctrl+A`) and the dashboard "Recent activity" card.
- **Per-package version history**: the detail modal already has a `get_history` table with the
  installed version highlighted (the downgrade entry point lives there).
- **Rollback handlers**: `window.installApp(id)` and `window.downgradeApp(id)` take a
  `"{type}:{name}"` id and route through the normal preview → root-password → terminal flow.
  `AtlasApi._get_pkg(id)` self-heals by searching when the id isn't in the in-memory registry, so
  an id reconstructed from an old activity entry still resolves.

## Increment 1 — Activity page → a usable history (frontend-heavy, low risk)

Goal: turn the flat feed into something you can *navigate and act on*, without a backend rewrite.

1. **Bigger window.** `get_activity` returns up to 50; bump the read to ~200 so filtering is
   meaningful (the file is tiny JSONL; keep newest-first). One-line backend change
   (`get_activity_log(limit=...)`).
2. **Filters** (pure, Node-VM-tested `filterActivity(entries, {action, type, query})`):
   - action chips: All / Install / Update / Uninstall / Downgrade (+ any other action present);
   - type filter: All + the source types actually present (arch / aur / flatpak / …);
   - free-text package-name search.
   They compose; filtering is client-side on the already-fetched list (instant).
3. **Date grouping** (pure `groupActivityByDate(entries, now)`): Today / Yesterday / Earlier this
   week / Older, each a labelled section. Keeps a long history scannable.
4. **Per-entry rollback affordances** (reuse existing handlers; reconstruct `id = type:name`):
   - **Downgrade** on a successful install/update/downgrade of an Arch/AUR package
     (`downgradeApp(id)`);
   - **Reinstall** on an uninstall entry (`installApp(id)`);
   - clicking the package name runs a **search** for it (navigates to results) as the "view" path
     (the detail modal needs a serialized pkg the feed doesn't carry; search re-resolves it).
   Actions are advisory entry points — they route through the existing preview/terminal flow, so
   nothing privileged happens without the usual confirmation.
5. Keep the unified empty/error state; keep the `navEpoch` stale-render guard.

Pure helpers (`filterActivity`, `groupActivityByDate`, and a small `activityEntryActions(entry)`
that decides which buttons an entry gets) are unit-tested in the JS contract harness; the DOM
wiring (chips, search, click handlers) is exercised by a flow test where practical.

## Deferred to later increments

- **pacman-log links** — surface the matching `/var/log/pacman.log` lines for an Arch entry
  (needs a backend reader + time/name matching; more involved, separate increment).
- **Per-package History tab on the page** (the detail modal already covers version history).
- **Log management** — clear / export the activity log; cap its size.

## Verification

- `python -m pytest` green; JS contract harness green (new helper tests).
- **Needs a GUI eyeball**: filters compose, date groups render, Downgrade/Reinstall route through
  the preview + terminal, package-name search navigates.
