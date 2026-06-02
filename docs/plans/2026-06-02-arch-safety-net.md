# Arch safety net — News page + .pacnew detection

**Date:** 2026-06-02
**Status:** done (2026-06-02)
**Scope:** two distinct, very-Arch features that warn users before/after system changes.
Decided behaviour (from the user): a **dedicated News page** (no update-flow blocking), and
`.pacnew`/`.pacsave` **detect-and-list with guidance** (read-only, no auto-merge).

## Why
Arch occasionally ships changes that need manual intervention (announced on archlinux.org
news), and updates drop `.pacnew`/`.pacsave` config files that silently need merging.
Neither is surfaced anywhere in a typical GUI. CachyOS (the dev box) is Arch-based and
tracks Arch, so archlinux.org news still applies.

## Part A — News page

**Backend** (`AtlasApi`):
- `get_arch_news(limit=12) -> dict` — GET `https://archlinux.org/feeds/news/` via the shared
  `HttpClient` (reached through the arch manager's `context.http_client`, with a fresh
  `HttpClient(self.logger)` fallback). Parse the RSS 2.0 (`channel/item`:
  `title`/`link`/`pubDate`/`description`) with stdlib `xml.etree.ElementTree`. Strip HTML
  from the description (`_strip_html`) and truncate to a short summary; format `pubDate`
  (RFC-822 → `parsedate_to_datetime`) to a friendly `MMM DD, YYYY`. Returns
  `{status, data:[{title, url, date, summary}]}`; network/parse failure → `{status:'error'}`.
  Read-only, no root. The feed fetch is the only network call.

**Frontend**:
- New sidebar nav item `data-view="news"` (icon + label) in `index.html`.
- `activateView('news')` → `renderNews()` (like `settings`): fetch `get_arch_news`, render a
  list of news cards (title links out via `open_url`, date, summary). Loading / empty /
  error states.

## Part B — .pacnew / .pacsave detection

**Backend** (`AtlasApi`):
- `get_pacnew_files() -> dict` — `find /etc /boot -type f \( -name '*.pacnew' -o -name
  '*.pacsave' \)` via `run_cmd(..., ignore_return_code=True, print_error=False)` (find
  returns non-zero on permission-denied subdirs; we ignore that). Listing by **name** needs
  no file-content reads and no root. Returns `{status, data:{files:[...], count:N}}`.
  Scanning `/etc`+`/boot` is fast and covers essentially all real cases; the guidance points
  at `pacdiff` as the authoritative tool for anything elsewhere.

**Frontend**:
- A `#updates-notice` element above `#packages-grid` (`index.html`). On the **Updates** view,
  `renderUpdatesNotice()` calls `get_pacnew_files`; if `count>0` it shows a warning card
  listing the files + guidance: "These `.pacnew` files were installed alongside updates.
  Review and merge them with `sudo pacdiff` (from `pacman-contrib`), then remove the
  `.pacnew`." Cleared when leaving the Updates view. Read-only — no merge/delete from the UI.

## Tests (`tests/view/webview/test_api.py`)
- `get_arch_news` parses a captured RSS fixture (`tests/.../resources/arch_news_feed.xml`)
  into the expected shape; HTML stripped from summary; bad/empty feed → `error`.
- `get_pacnew_files` parses mocked `find` output into `{files, count}`; empty → count 0.

## Out of scope (noted)
- Blocking/gating updates on unread news (chose a passive News page instead).
- Auto-merging `.pacnew` (launching pacdiff/editor) — detect & guide only.
- Per-news "is this newer than my last update" diffing (no reliable last-update timestamp
  surfaced yet; the page just shows recent news).
