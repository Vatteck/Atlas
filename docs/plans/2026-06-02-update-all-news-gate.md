# Gate "Update All" on Arch news — 2026-06-02

> **Status: implemented (2026-06-02).** Backend `check_upgrade_news` + `_last_db_sync_time` +
> `_fetch_arch_news_items` refactor (`api.py`); client-side `#news-gate-modal` + `showNewsGate`
> gating the Update All handler (`main.js`/`index.html`/`style.css`). Tests:
> `test_api.py::ArchSafetyNetTest` (5 new). Live-verified against the real feed + sync state.
> Needs a GUI eyeball on the modal (and unread news present to see it fire).

## Goal

Before a full system upgrade, surface recent **archlinux.org news** the user may not have read,
so they don't blindly `-Syu` into a known manual-intervention (the classic "you didn't read the
news and pacman broke" footgun). On-brand Arch safety-net feature.

## Behaviour

When the user clicks **Update All**:
1. Fetch recent Arch news and compare each item's publish date to a **reference time** = the last
   time the local pacman databases were synced.
2. If any news is newer than that reference, show a **blocking gate modal** listing those items
   (title · date · summary · "Read on archlinux.org" link → opens in the system browser via the
   existing `open_url`). Two buttons: **Proceed with upgrade** / **Cancel**.
3. If the user proceeds → run `update_all` as today. If they cancel → abort, no upgrade.
4. **Fail-open:** if the news check errors (offline, feed down) or finds nothing new, the upgrade
   proceeds normally — we never block an upgrade because the *check* failed.

### Reference time = last DB sync

Use the newest mtime among `/var/lib/pacman/sync/*.db` — those files are rewritten by `pacman
-Sy`, so their mtime is exactly "when the repos were last synced." Simple and reliable; no log
parsing. Fallback if unreadable/missing: **now − 7 days** (still surfaces very recent news rather
than silently showing nothing). Timezone-safe: mtime → aware UTC datetime; RSS `pubDate` is
already tz-aware (naive dates are treated as UTC defensively).

Rationale for "last sync" over "last upgrade": Atlas's Update All does `-Syu`, so the previous
sync marks the repo state the user last saw; news published since then is what's potentially
relevant to the upgrade they're about to run.

## Backend (`atlas/view/webview/api.py`)

- Refactor the RSS parse out of `get_arch_news` into `_fetch_arch_news_items(limit)` → list of
  `{title, url, date (display str), summary, dt (aware datetime|None)}`. `get_arch_news` keeps its
  current shape (drops `dt`); single source of truth for parsing.
- `_last_db_sync_time()` → aware `datetime|None` (max mtime of `/var/lib/pacman/sync/*.db`).
- `check_upgrade_news(limit=12)` → `{status, data: {since: iso|null, new_count: int,
  news: [ {title,url,date,summary} ]}}` — `news` holds only the items newer than the reference.

## Frontend (`main.js` / `index.html` / `style.css`)

- New self-contained, **promise-based** `#news-gate-modal` (the existing confirm modal is wired to
  the Python watcher via `submit_confirmation`, so it can't be reused for a client-only decision).
  `showNewsGate(items) -> Promise<bool>`. Reuses the `.news-card` markup/styles from the News page;
  links routed through `pyApiCall('open_url', …)`.
- `updateAllBtn` handler: `const n = await pyApiCall('check_upgrade_news'); if (n && n.new_count) {
  if (!await showNewsGate(n.news)) { abort } }` then proceed to `update_all`.

## Tests (`tests/view/webview/test_api.py`)

- `check_upgrade_news` filters to items newer than the reference (mock `_http_client` with a small
  RSS payload + monkeypatch `_last_db_sync_time`); fail-open on feed error; empty when nothing new.
- `_last_db_sync_time` returns None cleanly when the sync dir is absent (no crash).

## Out of scope / notes

- Not persisting "read" state (informant-style acknowledgement DB) — the sync-time heuristic is
  simpler and good enough. Could revisit if it proves noisy.
- Only gates **Update All**, not per-package updates (single updates rarely hit news intervention).
