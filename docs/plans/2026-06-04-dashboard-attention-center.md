# 2026-06-04 — Dashboard "Attention Center"

From BACKLOG → Open work (the product-vision centerpiece). Make the dashboard answer
**"what needs my attention today?"** with a row of lazy, best-effort cards above the existing
app-suggestions grid. Each card: a status, a one-line detail, and one click-through to the page
that acts on it.

## Principles (from the roadmap)

- **Lazy / best-effort / fail-open.** Cards never block dashboard load; skeletons show first.
  Any failed signal shows "couldn't check", not an error — the dashboard must always render.
- **No new engine work.** Aggregate signals that already exist; don't add new system probes.
- **Cheap on the main path.** The one expensive signal (updates = `read_installed`) loads
  independently so it can't delay the cheap cards.

## Cards (v1)

1. **Updates** — count + Arch/AUR/Flatpak split; "everything up to date" success state at 0.
   Click → Updates view.
2. **System safety** — `.pacnew` count, DB-sync age, pacman lock, news published since last
   sync. Click → News (if unread news) else Updates.
3. **Reclaim space** — orphan count, pacman cache size, unused-Flatpak-runtime availability.
   Click → Disk view.
4. **Recent activity** — last ~3 install/update/uninstall entries. Click → Activity view.
5. **AUR safety** — clean-chroot enabled? devtools available? Click → Settings.

Deferred to a follow-up: a **Flatpak permissions** "risky apps" card — counting risky installed
Flatpaks needs per-app permission reads (expensive) and `read_installed`, which violates the
cheap-path rule. A no-count shortcut card adds little, so it's left out of v1.

## Backend

New `AtlasApi.get_dashboard_summary()` — runs the **cheap** signals concurrently on the existing
`self._executor` and returns one fail-open payload (each sub-check wrapped; failure → `None`):

```
{status:'ok', data:{
  safety:  {pacnew_count, db_sync_age_hours, pacman_locked, news_count},   # any may be None
  reclaim: {orphans, cache_human, flatpak_available},
  aur:     {chroot_enabled, chroot_available},
  activity:[ {action, pkg_name, pkg_type, success, timestamp} x3 ],
}}
```

- Reuses `get_pacnew_files`, `check_upgrade_news`, `get_cleanup_summary`, `get_activity`, and the
  arch block of `get_app_settings` (chroot enabled/available). DB-sync age from
  `_last_db_sync_time()`; pacman lock = `os.path.exists('/var/lib/pacman/db.lck')`.
- **Updates are NOT in this payload** — the frontend calls `get_updates` separately (expensive),
  reusing the existing `packageCache` when warm, and fills the Updates card late.

## Frontend

- `index.html`: a `#attention-center` container before `#packages-grid` (cleared on every view
  change, like `#updates-notice`).
- `main.js`: `renderAttentionCenter()` — injects 5 skeleton cards, then fires
  `get_dashboard_summary` + `get_updates` in parallel and fills cards as they resolve. The pure
  HTML builder is a separate function (`buildAttentionCardsHTML(summary)` /
  `buildUpdatesCardHTML(updates)`) so it can be unit-tested in the Node VM contract harness.
  Hooked into the dashboard branch of `activateView`/`fetchPackages`; suggestions still load below.
- `style.css`: `.attention-center` (responsive grid), `.attention-card` (status tone classes:
  ok/warn/info), skeleton shimmer reuse.

## Tests

- `test_api.py::DashboardSummaryTest` — aggregation shape; each sub-check failing → that field
  `None` while `status` stays `ok` (fail-open); chroot/news/reclaim wiring with mocked gems.
- `main_js_contracts.test.js` — `buildAttentionCardsHTML` renders the expected cards/tones for a
  representative summary, and the empty/"couldn't check" path.

## Revision after GUI feedback (2026-06-04)

First cut stacked the cards above the suggestions grid; the two card-grids blended together. Per
the user's call, **the dashboard is now the Attention Center only** — the app-suggestions grid was
removed from the dashboard and **moved to Browse** as a "Suggested for you" row above the category
grid (real package cards, reusing the `#packages-grid` click delegation via a shared
`appendPackageCards()` helper). App discovery now lives entirely in Browse + Installed + search.
Card tone also moved off a one-side colored stripe onto a **tinted circular icon chip** (matching
the detail-modal badge language), and the grid got the same 24px inset as `.packages-grid` so the
cards line up instead of bleeding under the sidebar / off the right edge. Cards were later made
**richer** (a big hero metric — update count / GB to reclaim / On-Off — plus subtitle and source
chips, taller cards) and topped with a **dashboard header**: a time-of-day greeting
(`dashboardGreeting`) + a status line whose actionable count (`countActionable`, mirroring the
warn-tone cards) drives the message (`dashboardMessage`). On Browse, **categories render above** the
"Suggested for you" row, and the Development/System category glyphs were swapped to color-emoji
(💻 / ⚙️) since the originals were faint text-presentation glyphs.

## Verification

`python -m pytest` green (454); Node contract harness green (10, incl. dashboard-has-no-packages
and Browse-renders-suggested-row). **Needs a GUI eyeball** (card layout + live signals +
click-through; Browse suggested row — can't be driven headless).
