# STATUS — the handoff baton

> **This is the single most important file for cross-agent continuity.** It is the live
> state of the project. Read it at the start of every session; update it at the end of
> every session that changes code (see AGENTS.md §8). Keep it short and current — when an
> item is stale, fix it or delete it.

**Last updated:** 2026-06-02 (starting system-tray indicator)
**Version:** 0.10.7
**Working branch:** `master` (use short-lived branches for larger features; run `git branch` to see what's active)

> Feature wishlist lives in **[BACKLOG.md](BACKLOG.md)** — the longer-horizon menu we pull
> from. This file stays the live baton (in-progress / just-shipped).

---

## Current focus

**Arch safety-net features (2026-06-02).** The big transitions are done; Atlas is an Arch-focused,
**pure-Python** pywebview app on the AUR with green CI. Now building out the feature backlog.
Recently shipped the **non-Qt system tray** (icon + update badge + Settings), **Browse by
category**, **grid/list toggle**, **sort dropdown**, the **window-icon fix**, the **new app icon**,
and **AUR publish automation**. **Just built:** an **Update-All news gate** (warns about
archlinux.org news since the last sync before a full upgrade) — see Done. Next likely the
`.pacnew` merge-assist follow-up.

## Next

Pulling from **[BACKLOG.md](BACKLOG.md)**. Near-term candidates:

- **AUR safety theme (in progress):** layered defense for AUR installs. ✅ Heuristic PKGBUILD
  scanner *engine* landed (see Done). **Next increment:** wire it into the PKGBUILD review UI +
  add a **diff-since-last-build** view (layer 1 — `git.diff` helper + last-built-commit lookup).
  Later: **sandboxed chroot builds** (layer 3 —
  [plans/2026-06-02-sandboxed-aur-builds.md](plans/2026-06-02-sandboxed-aur-builds.md)). Honest
  framing throughout: these are *helpers*, not malware detection (don't auto-block / show "safe").
- ✅ **Arch safety net (system-level) is done** — Update-All news gate + `.pacnew` merge-assist button.
- Note: **keyboard shortcuts** and the **selection toolbar** backlog items already look largely
  shipped (shortcuts help button + batch install/uninstall bar) — confirm before re-picking.

> GUI-verified 2026-06-02: rich detail modal (screenshots + history), News page, Disk
> maintenance panel all look good. Still worth a live run: an actual **downgrade**
> (privileged + may prompt for a version), the new **screenshot lightbox**, and the new
> **Browse** page (category grid → package grid; can't be driven headless).
- Exploratory: container sandboxing ("Vault").
- Lower-value: route the controller's ad-hoc `Thread(...)` spawns through a shared pool
  (marginal; only with a measured reason).

Done this session: ✅ CI (GitHub Actions, pytest 3.10–3.13), ✅ dropped Rust, ✅ deleted the
dead Qt-era settings tree, ✅ refreshed stale metadata, ✅ Arch PKGBUILD
(`linux_dist/arch/PKGBUILD`; wheel build verified — pure-Python `py3-none-any`).

The Rust verdict (kept as a lesson): native code only pays off for **CPU-bound ops with a
small result**; Atlas has almost none (it waits on pacman/AUR/network/makepkg). Don't
re-add a native extension without a measured win. Details in the historical
[ROADMAP.md](ROADMAP.md).

---

## Done

- **Fix: AUR installs crashed in the webview (`file_downloader=None`) (2026-06-02):** every AUR
  install/build threw `AttributeError: 'NoneType' object has no attribute 'is_multithreaded'` —
  `_pre_download_source` called `self.context.file_downloader.is_multithreaded()`, but the webview
  builds its `ApplicationContext` with **`file_downloader=None`** (`app.py`), and pre-downloading
  sources is just a multithreaded optimization. Guarded both call sites: `_pre_download_source`
  (skips the optimization → makepkg fetches sources itself during the build) and
  `_multithreaded_download_enabled` (was only shielded by the default-off
  `repositories_mthread_download`; would crash if toggled on). Surfaced now because it was the first
  AUR install attempted through the webview (tuxracer). Tests: `tests/gems/arch/test_downloader_guard.py`
  (2). **Re-test needed:** confirm an AUR build now completes end-to-end (the crash is gone; build
  itself is privileged/network so wasn't run here).
- **`.pacnew` mirrorlist caution (2026-06-02):** the `.pacnew` notice now shows a pointed warning
  when `/etc/pacman.d/mirrorlist` is among the flagged files — overwriting it with pacdiff replaces
  your servers with the stock all-commented list (a user hit exactly this while testing the pacdiff
  button). Steers to regenerate or discard the `.pacnew`, and (when mirrorlist is flagged) offers a
  **"Regenerate mirror list" button**: `AtlasApi.regenerate_mirrorlist()` runs **reflector**
  (`--protocol https --latest 20 --sort rate --download-timeout 5 --save /etc/pacman.d/mirrorlist`;
  rate-mirrors fallback; *not* cachyos-rate-mirrors — that targets the CachyOS list) via the root
  broker. The Arch-correct counterpart to the dead Manjaro `refresh_mirrors` (Known gaps). Tests:
  `test_api.py::ArchSafetyNetTest` (+4). Live-verified the command matches what fixed a real box.
  Also exposed an **always-available "Regenerate mirror list" button in Settings → Mirrors** (not
  just the `.pacnew` caution): shared `regenerateMirrors()` JS helper; `get_app_settings` arch block
  now reports `mirror_tool` so the button disables with an "install reflector" hint when no tool is
  found. Still TODO: fix the *gem's* `refresh_mirrors` custom action too —
  [plans/2026-06-02-arch-mirror-refresh.md](plans/2026-06-02-arch-mirror-refresh.md).
- **AUR safety — heuristic PKGBUILD scanner engine (2026-06-02):** first increment of the "AUR
  safety" theme. New pure module `atlas/gems/arch/pkgbuild_audit.py` — `scan(text)` returns advisory
  findings (`{line_no, line, rule, severity, why}`) for suspicious PKGBUILD/.install constructs:
  pipe-to-shell, base64 (+ long base64 blobs, excluding hex checksums), eval, hex-escape runs,
  network commands in the build, sensitive-path writes (ssh/dotfiles/sudoers/crontab/autostart),
  setuid, sudo, and dangerous `rm -rf` (only on `~`/`$HOME`/absolute paths, **not** `$srcdir`).
  AI-free, no network. **Explicitly a helper, not a verdict** (`DISCLAIMER` const) — must never
  auto-block or show "safe". Tuned against false positives (benign PKGBUILD → 0 findings).
  Tests: `tests/gems/arch/test_pkgbuild_audit.py` (14, incl. benign-lookalike non-firing cases).
  **Wired into the build flow (2026-06-02):** `ArchManager._audit_pkgbuild(context)` runs in `_build`
  (after the edit step, before makepkg) and scans the PKGBUILD + `*.install`. If anything is flagged
  it shows an **advisory `request_confirmation`** ("Build anyway?" / "Cancel") listing the lines +
  the disclaimer — surfacing even when `edit_aur_pkgbuild` is off, so it helps the people who skip.
  Silent (no prompt) when clean. Gated by new config `aur_check_pkgbuild` (default **True**); cancel
  aborts the build. Added `white-space: pre-wrap` to `#confirm-message`/`#message-body` so the
  multi-line advisory renders. Tests: `tests/gems/arch/test_pkgbuild_audit_gate.py` (6). **Behavior
  change to AUR installs — needs a GUI eyeball** (flagged pkg → advisory appears; clean pkg → no
  interruption). A **Settings toggle** ("AUR safety → Scan PKGBUILDs before building") now exposes
  `aur_check_pkgbuild` via the webview Settings page (`get_app_settings`/`save_app_settings` gained an
  `arch` block; `test_api.py::AppSettingsTest` +2). **Layer 1 — diff-since-last-build (2026-06-03):**
  on an AUR **update**, the audit advisory now also shows *what changed* in the PKGBUILD since the
  last build (the compromised-release guard). The fresh clone is shallow (`depth=1`), so the old
  revision is fetched from **AUR cgit** by commit (`…/plain/PKGBUILD?h=<base>&id=<pkg.commit>`,
  best-effort via `http_client`; `pkg.commit` is already persisted) and diffed in Python
  (`pkgbuild_audit.diff`, truncated). The advisory now fires on **findings OR a non-empty update
  diff**; body shows the diff + flagged lines + disclaimer. Fresh installs unchanged (prompt only on
  findings). Live-verified vs real AUR (injected `curl|bash` shows as a `+` line *and* trips the
  scanner). Tests: `test_pkgbuild_audit.py` (+3) + `test_pkgbuild_audit_gate.py` (+3). Note: this
  means AUR updates with PKGBUILD changes now prompt (toggle: `aur_check_pkgbuild`); update-all noise
  is the known tradeoff. Design:
  [plans/2026-06-02-aur-pkgbuild-review.md](plans/2026-06-02-aur-pkgbuild-review.md). The chroot-build
  layer is a separate design note ([plans/2026-06-02-sandboxed-aur-builds.md](plans/2026-06-02-sandboxed-aur-builds.md)),
  not started.
- **`.pacnew` merge assist (2026-06-02):** the `.pacnew`/`.pacsave` notice on the Updates view now
  has an **"Open pacdiff in a terminal"** button. Backend (`api.py`): `_find_terminal()` resolves an
  available emulator (honors `$TERMINAL`, then a curated list whose exec flag takes args separately:
  `konsole -e`, `gnome-terminal --`, `alacritty -e`, `kitty`, `foot`, `wezterm start --`,
  `xfce4-terminal -x`, `xterm -e`), and `launch_pacdiff()` spawns `[*term, 'sudo', 'pacdiff']`
  detached (`start_new_session=True`). Errors cleanly if `pacdiff` is missing (→ install
  pacman-contrib) or no terminal is found. We only *launch* the standard tool — no merging/removal
  inside Atlas. Frontend: button in `renderUpdatesNotice` + `.config-notice-actions` style. Tests:
  `test_api.py::ArchSafetyNetTest` (3 new). Terminal resolution verified live (`konsole -e`); the
  actual launch needs a GUI eyeball (opens a sudo terminal). Plan:
  [plans/2026-06-02-pacnew-merge-assist.md](plans/2026-06-02-pacnew-merge-assist.md).
- **Gate "Update All" on Arch news (2026-06-02):** before a full upgrade, warn about
  archlinux.org news published since the last DB sync (the "didn't read the news, pacman broke"
  guard). Backend (`api.py`): `_fetch_arch_news_items()` (shared RSS parser, now also keeps a raw
  aware `datetime`; `get_arch_news` reuses it and strips `dt`), `_last_db_sync_time()` (newest
  mtime of `/var/lib/pacman/sync/*.db`; fallback now−7d), and `check_upgrade_news()` →
  `{since, new_count, news[]}` (only items newer than the reference). **Fail-open**: any feed/parse
  error returns an empty result so the upgrade is never blocked by the *check* failing. Frontend: a
  self-contained, promise-based `#news-gate-modal` + `showNewsGate()` (the confirm modal is wired
  to the Python watcher, so it can't be reused) reusing `.news-card` markup; links open via
  `open_url`. The Update All handler calls `check_upgrade_news` first and gates on it. Tests:
  `test_api.py::ArchSafetyNetTest` (5 new). Live-verified vs the real feed + sync state. Plan:
  [plans/2026-06-02-update-all-news-gate.md](plans/2026-06-02-update-all-news-gate.md). **Needs a
  GUI eyeball** (modal render + proceed/cancel; requires unread news to actually fire).
- **System tray — phase 2 (update badge) + Settings UI (2026-06-02):** the tray now shows a
  pending-update **count**. A daemon-thread poller (`ui.tray.update_check_interval` minutes,
  default 60, 0=off; first run 30s after build) calls `manager.read_installed()`, counts
  `p.update`, and pushes the number to the GTK thread via `GLib.idle_add`. Poller stops cleanly
  on Quit (`threading.Event`). Also added a **System tray** section to the webview Settings page
  (`AtlasApi.get_app_settings`/`save_app_settings` gained a `tray` block; `renderSettings`/
  `saveSettings` + a `.styled-input` CSS rule): toggle the icon, close-to-tray, and the interval
  — greyed out when the AppIndicator backend is absent; **changes apply on next launch**.
  **Visibility fixes after a GUI eyeball (KDE only updated on right-click; in-app count only
  after opening Updates) — and two regressions those first fixes caused, now corrected:**
  - **KDE ignores `set_label`** (Unity/GNOME-only), so the count was invisible until you opened
    the menu. Now we **draw the count onto the icon**: cairo composites a red badge bubble
    (capped "99+") over the logo, written to a temp PNG, and the indicator swaps to it via
    `set_icon_full(<absolute-path>)` — an absolute path makes AppIndicator send pixmap data,
    which is the **only** thing KDE's SNI host reliably shows. The zero state restores the proven
    **themed name** (`atlas-pm`), so the base icon never regresses. `set_label` kept (helps
    Unity/GNOME). Temp dir cleaned on Quit. *(First attempt used `set_icon_theme_path` + a bare
    name → KDE showed the "A" letter-avatar; abandoned.)*
  - **Don't call `evaluate_js` on the GTK main thread.** pywebview's `evaluate_js` blocks the
    caller on a semaphore the main loop must release, so calling it from `_apply_count` (which
    runs via `GLib.idle_add` on the main thread) **deadlocked the UI** ("application not
    responding"). Now the webview push (`_push_badge_to_webview`) runs on the poller's background
    thread, and `_on_updates` navigation runs on a worker thread too. `_apply_count` is GTK-only.
    **This is a general gotcha — see Known gaps.**
  - **In-app sidebar badge is now proactive:** `setUpdatesBadge()`/`refreshUpdatesBadge()` in
    `main.js` populate `#updates-badge` at startup and after update/update-all (not only when the
    Updates page loads); hidden at 0 (default `display:none` in `index.html`). The tray poller
    also calls `window.setUpdatesBadge(n)` so the sidebar stays live while the window is open.
  Tests: `tests/view/test_tray.py` (21) + `test_api.py::AppSettingsTest` (4 new). Smoke-tested on
  a real GTK loop: poller→count, badge-icon render (incl. "99+" cap), absolute-path icon set,
  `evaluate_js` confirmed off the main thread, temp cleanup. **Needs a GUI eyeball on KDE** to
  confirm the icon badge is visible passively and the ANR is gone.
- **Fix `_fill_suggestions` crash on an empty/partial config file (2026-06-02):** a background
  thread threw `TypeError: 'NoneType' object is not subscriptable` (non-fatal — logged, app kept
  running). Root cause: `_fill_suggestions` passed `self.configman.read_config()` to the
  suggestions downloader, but `YAMLConfigManager.read_config()` returns **None** when the config
  file exists yet is empty/null (`yaml.safe_load → None`); `should_download` then indexed a
  default key (`arch_config['suggestions_exp']`) on None. Fix: pass **`get_config()`** (defaults
  merged with cached — never None) instead. Same one-liner applied to the **Debian** gem
  (`debian/controller.py:541`, identical pattern; off by default but same latent crash). Sibling
  of the 2026-06-01 `deep_update` null-override fix. Tests: `tests/common/test_config.py` (5 —
  locks the `read_config()`-is-None-vs-`get_config()`-defaults contract).
- **System-tray indicator (non-Qt) — phase 1 (2026-06-02):** reintroduced a tray presence,
  this time pure-Python (the legacy Qt tray was purged). Backend: **AyatanaAppIndicator3** (falls
  back to AppIndicator3) via `gi` — a StatusNotifierItem KDE Plasma shows natively; rides the
  same GTK3 loop pywebview runs, no Qt, no new Python dep (system pkg `libayatana-appindicator`).
  New `atlas/view/tray.py` (`AtlasTray` + `start()` factory); wired in `app.py` before
  `webview.start()` (the indicator builds on the GTK loop via `GLib.idle_add`, so pre-start
  wiring is fine). Menu: **Show/Hide Atlas**, **Check for updates** (→ `activateView('updates')`),
  **Quit Atlas** (`window.destroy()` = real exit). **Close-to-tray** is opt-in: a `closing`
  handler returns `False` to cancel the close and hide instead, gated on the new
  `ui.tray.minimize_to_tray` (default **off** → closing quits as before). Also new:
  `ui.tray.enabled` (default on). Fully **additive/optional** — missing typelib or
  `enabled:false` → `start()` no-ops and the app launches unchanged. Tests:
  `tests/view/test_tray.py` (12, pure-logic helpers + callback behaviour with a fake window).
  Smoke-tested on a real GTK loop (indicator builds, callbacks don't crash). **GUI-confirmed
  working on KDE by the user (2026-06-02).** Plan:
  [plans/2026-06-02-system-tray.md](plans/2026-06-02-system-tray.md).
- **New app icon (2026-06-02):** replaced the app logo with a new `icon.svg` provided by the
  user. `atlas/view/resources/img/logo.svg` now holds the new vector; `logo.png` re-rasterized
  from it at 512×512 (`rsvg-convert`) — that's the window icon (`app.py`) and the `atlas-pm`
  icon the PKGBUILD installs to hicolor/pixmaps. Removed the orphaned `logo_update.svg` (a
  leftover bauh asset, zero references). No code paths changed. Commit `3d59189`. Verified live
  on a clean CachyOS+Plasma box (new icon shows first launch). One stale second machine showed
  the old map icon (app_id correctly `atlas-pm` but KWin fuzzy-matched a stale local desktop
  file) — purely local cache/leftover state, not a code/packaging issue; deferred.
- **Window icon — make the identity uniformly `atlas-pm` (2026-06-02):** the prior fix pinned
  app_id to the bare **`atlas`**, which still showed the map on KDE/Plasma Wayland. Diagnosis
  from the affected box: install was correct (Icon=atlas-pm, StartupWMClass, atlas-pm.png all
  present) but the active icon theme ships a generic **`atlas`** icon (char-white, Tela,
  Fluent, WhiteSur, BigSur-black all carry `…/apps/atlas.svg` — a map), and KDE resolves a
  window's icon by an **app_id→icon-name lookup** that hit the theme `atlas` *before* the
  desktop file's `Icon=`. Fix: drop the bare `atlas` identity entirely — `set_prgname('atlas-pm')`,
  renamed the entry to **`atlas-pm.desktop`** (so app_id == desktop basename), `StartupWMClass=atlas-pm`,
  `Icon=atlas-pm` (unchanged); the PKGBUILD installs `atlas-pm.desktop`. `atlas-pm` collides with
  no theme. Verified app_id flips to `atlas-pm` (throwaway GTK window). Also forced the GTK
  backend (`gui='gtk'` unless `PYWEBVIEW_GUI` set) so pywebview doesn't try Qt first (the
  affected box has no qtpy → scary-but-harmless traceback) and so the GTK app_id always applies.
  **Needs a relogin + `kbuildsycoca6` on KDE after rebuild** for the cache to refresh.
- **Sort dropdown (2026-06-02):** a topbar `#sort-filter` (next to the type filter / view
  toggle) — **Relevance** (default; unchanged search/AUR ranking), **Votes**, **Popularity**,
  **Recently updated**, **Name (A–Z)**. Client-side in `main.js` (`sortPackages()` dispatch +
  `sortMode` persisted to `localStorage['atlas_sort_mode']`); `renderFiltered()` and
  `renderCategoryPackages()` both route through it. Explicit modes override search relevance;
  missing numeric keys (votes/popularity/`last_modified` on non-AUR sources) sort last. Backend:
  one line — `last_modified` (epoch, AUR-populated) added to `_serialize_pkg`. Live re-sort
  covers dashboard/installed/updates/search; Browse applies on category (re)open (documented
  limitation). Tests: `test_api.py::SerializeSortFieldsTest` (1). Plan:
  [plans/2026-06-02-sort-dropdown.md](plans/2026-06-02-sort-dropdown.md). **Needs a GUI eyeball.**
- **Window icon — fix the running-window "map" icon, incl. Wayland (2026-06-02):** the earlier
  icon fixes (`Icon=atlas-pm` + shipping `atlas-pm.png`, commits `fc9331e`/`b0e09c4`) only
  covered the **launcher** `.desktop` entry. The **running window** (titlebar / taskbar /
  dock / alt-tab) fell back to a generic `atlas` **map** icon some themes ship (e.g. CachyOS's
  `char-white` → `/usr/share/icons/char-white/apps/16/atlas.svg`). Two-pronged fix in `app.py`:
  - **Wayland (the important one):** the compositor/dock/switcher resolves a window's icon by
    matching its **app_id to a `.desktop` file**, *not* the client-set GTK icon. GTK derives
    the app_id from the program name, which defaulted to `argv[0]`'s basename — **`app.py`**
    under `python -m atlas.app` (verified live via `hyprctl clients`: `class='app.py'`,
    native Wayland) — matching no desktop file → fallback icon. `GLib.set_prgname('atlas')`
    pins app_id=`atlas`, which matches `atlas.desktop` (→ `Icon=atlas-pm`). Verified with a
    throwaway GTK window: `class` flips `app.py` → `atlas`.
  - **X11 complement:** pass the bundled 512×512 logo to `webview.start(icon=…)` (pywebview
    calls `set_icon_from_file` + `set_default_icon_from_file`). `icon` landed in **pywebview
    4.2**, so feature-detected via `inspect.signature`; dep floor bumped `>=4.0 → >=4.2`.
  - Also added `StartupWMClass=atlas` to `atlas.desktop` (belt-and-suspenders for WMs/
    compositors that match on it).
  This is a *runtime/code* fix (ships with source, not just the PKGBUILD). On Wayland the icon
  still resolves through the **installed** `atlas.desktop` + `atlas-pm.png` (hicolor), so a
  package install is still required for the bitmap. **Verified live (Hyprland/Wayland):** after
  relaunch `hyprctl clients` reports the Atlas window's `class` as `atlas` (was `app.py`), so
  the dock/switcher now matches `atlas.desktop`. The second CachyOS box's *launcher* icon is a
  separate install-side issue (rebuild the `-git` pkg + refresh icon cache).
- **Grid/list layout toggle (2026-06-02):** package views were a CSS grid
  (`minmax(300px, 1fr)`) that auto-collapsed to one column on narrow panes — which read as
  an inconsistent "sometimes list, sometimes grid". Added an explicit segmented **toggle** in
  the topbar (grid/list icons next to the type filter) so layout is the user's choice, not
  width-driven. List mode is one full-width row per package (icon+title · description ·
  tags/actions). Pure CSS — `applyViewMode()` toggles `.view-list` on `#packages-grid` (no
  refetch/re-render), `setViewMode()` persists to `localStorage['atlas_view_mode']`, re-applied
  in `renderPackages` + on launch. Files: `index.html` (`#view-toggle`), `main.js`, `style.css`
  (`.view-toggle`, `.view-list .package-*`). Frontend-only (no Python tests). GUI-confirmed by
  user. Note: categories are still only surfaced on the Browse page (each pkg carries
  `categories` but cards/detail don't show them yet — possible follow-up).
- **Browse by category — store-like discovery view (2026-06-02):** a new **Browse** sidebar
  page. Atlas already cached `categories.txt` (name → raw category labels, ~294 entries) but
  only used it to *annotate* search results; now it's a browse index. `AtlasApi.get_categories`
  normalizes the messy raw labels (Browser/browser, Xfce/XFCE, Python, Emulator, Manjaro, …)
  into 8 curated top-level buckets (`CATEGORY_BUCKETS`: Games / Internet / Audio & Video /
  Graphics / Development / Office / Utilities / System) with distinct-package counts; every
  raw label maps into a bucket (verified against the live file). `get_category_packages(key)`
  resolves a bucket's names through two new **Arch-gem** methods — `read_categories()` (returns
  `self.categories`, one-shot reads the cached file if the bg downloader hasn't run) and
  `list_category_packages(names)` (I/O-cheap: one `pacman -Sl` for version/repo/installed + one
  batched `pacman -Si` for descriptions; **no AUR RPC, no network**). Arch-only by design
  (categories.txt is a repo index). Frontend: `renderBrowse()` (category-card grid) →
  `renderCategoryPackages(key,label)` (back header + reuses `renderPackages`), nav item +
  `.category-card`/`.browse-*` styles. Tests: `test_api.py::BrowseCategoryTest` (4). Plan:
  [plans/2026-06-02-browse-by-category.md](plans/2026-06-02-browse-by-category.md). **Needs a
  GUI eyeball** (grid render can't be driven headless).
- **Downgrade / rollback (2026-06-02):** the gems implement `downgrade` and `_serialize_pkg`
  reports `can_be_downgraded`, but the webview never called it. Added `AtlasApi.downgrade`
  (mirrors `update`/`uninstall`: root broker → terminal → `manager.downgrade(pkg, …,
  handler=WebviewWatcher)` → activity + notify; the gem picks the target version and may
  prompt via the watcher). Frontend: a **Downgrade** button in the detail-modal footer (when
  installed + `can_be_downgraded`) + `window.downgradeApp`; `.activity-action.downgrade`
  badge style. Tests: `test_api.py::DowngradeTest` (3). Plan:
  [plans/2026-06-02-downgrade-rollback.md](plans/2026-06-02-downgrade-rollback.md). **Needs a
  GUI eyeball** (privileged transaction; may prompt for a version).
- **Rich app detail page — screenshots + version history (2026-06-02):** the detail modal
  was description + a key/value table only. The orchestrator already had `get_screenshots`
  (Flatpak/AppImage) and `get_history` (all gems) but neither was exposed to the webview —
  now wired as `AtlasApi.get_screenshots` / `get_history` (+ `has_screenshots` in
  `_serialize_pkg`). Frontend: `renderDetailScreenshots` (a lazy-loaded thumbnail strip,
  click opens the full image) and `renderDetailHistory` (a table built from the union of
  entry keys via the existing `prettifyInfoKey`, installed version's row highlighted) in
  `main.js`, with `#detail-screenshots` / `#detail-history-section` in `index.html` and
  `.screenshot-thumb` / `.history-table` styles. Tests: `test_api.py::RichDetailTest` (4).
  Plan: [plans/2026-06-02-rich-app-detail.md](plans/2026-06-02-rich-app-detail.md).
  **Needs a GUI eyeball** (strip/history can't be driven headless).
- **Arch safety net — News page + .pacnew detection (2026-06-02):** two distinctive,
  very-Arch features. A dedicated **News** sidebar page pulls recent archlinux.org news
  (`AtlasApi.get_arch_news` — fetches the RSS feed via the shared `HttpClient`, parses with
  stdlib `xml.etree`, strips HTML from summaries; `renderNews()` in `main.js`). And a
  **`.pacnew`/`.pacsave` notice** on the Updates view: `get_pacnew_files` runs
  `find /etc /boot -name '*.pacnew'/-name '*.pacsave'` (by name only — no content reads, no
  root), `renderUpdatesNotice()` shows a warning card listing them + `pacdiff` guidance
  (read-only, no auto-merge). Chosen behaviour: passive News page (no update gating),
  detect-and-list for `.pacnew`. Tests: `test_api.py::ArchSafetyNetTest` (6). Plan:
  [plans/2026-06-02-arch-safety-net.md](plans/2026-06-02-arch-safety-net.md). Verified live:
  feed parses (10 items), and the dev box has ~10 real `.pacnew`/`.pacsave` files.
- **Maintenance / Cleanup hub on the Disk view (2026-06-02):** turned the Disk view from
  informational into actionable. New "Reclaim space" panel surfaces the three big Arch
  space-wasters, each with an estimate + confirm step: **orphan packages** (reuses the
  existing `get_orphans` checklist flow, now extracted into `runOrphanCleanup()`), **pacman
  package cache** (`pacman -Sc` — keeps cache for installed pkgs so downgrades still work;
  freed amount measured by `get_dir_size` before/after since `pacman -Sc --print` needs
  root), and **unused Flatpak runtimes** (`flatpak uninstall --unused`, at the configured
  install level — `--user` no-root by default, `--system` under root). Backend: `AtlasApi.
  get_cleanup_summary` (cheap, read-only — no `read_installed`), `clean_pacman_cache`,
  `clean_flatpak_unused` in `view/webview/api.py`. Frontend: `renderMaintenancePanel`/
  `handleMaintenanceAction` in `main.js`, `.maintenance-*` styles. Tests:
  `test_api.py::CleanupHubTest` (7). Plan:
  [plans/2026-06-01-maintenance-hub.md](plans/2026-06-01-maintenance-hub.md). Backlog of
  further ideas captured in [BACKLOG.md](BACKLOG.md).
- **Bulk Selection Fix and Dynamic Batch Action Bar (2026-06-02):** Resolved a critical event propagation bug (`event.stopPropagation()`) in the package card checkbox template that blocked selection toggle events from reaching the grid event delegation layer, causing direct checkbox clicks to not update the selection count or visual selected styles. Additionally implemented fully dynamic batch action controls at the bottom overlay (`Install Selected (N)` / `Uninstall Selected (M)`) and engineered the corresponding sequential bulk installation backend API `batch_install` to support single-authentication multi-package installations. Fully verified via extensive new unit tests.
- **Clean Package Details Modal & Array Formatting (2026-06-02):** Fixed the bug where the package details modal displayed raw `"null"` values for missing metadata rows (such as conflicts, provides, and optional deps). Empty, `null`, `undefined`, and `"None"` / `"none"` / `"null"` values are now omitted from the details table entirely, keeping it clean and compact. Also formatted array values (such as "depends on" and "required by") as nice, clean comma-separated lists instead of raw JSON arrays.
- **Responsive Layout Adaptivity (2026-06-01):** Implemented fluid layout adaptivity to support tiling window managers and small splits down to 400px wide. Changed the pywebview minimum window constraint in `app.py` from `(800, 600)` to `(400, 400)` and shifted CSS media queries breakpoints upward (collapse at `960px`, stacking at `700px`, single-column grid at `520px`) to perfectly cover 1080p screen half-splits.
- **UI Polish & Micro-interactions (2026-06-01):** Implemented 7 high-performance, GPU-safe micro-interactions to elevate the UI's tactile feel: active navigation indicator spring bar, badge pop scale animation (`.badge-pop`), package card hover glow (`box-shadow`), source switcher scale-down on active, tactile button scale-down (`transform: scale`), toast custom slide-in/out scale animations tailored per success/error, and focus outline rings for keyboard accessibility.
- **UI Modernization & Premium Design Tokens (2026-06-01):** Implemented modern Obsidian/Deep Graphite surfaces and Indigo/Purple premium theme accents. Rebuilt CSS custom properties, added smooth transitions, glassmorphic sidebar and topbar, spring-ease obsidian blurred modals, animated loading skeleton screens, 3D lift package cards, and removed the awkward left active-nav border shadow. Fully tested and verified.
- **Scroll Performance Optimization (2026-06-01):** Fixed severe scroll lag in the package grid. Root causes were (1) the sticky `.topbar` with `backdrop-filter: blur(16px)` overlapping the scrolling packages grid, forcing expensive repaints (fixed by promoting to a compositor layer via `transform: translateZ(0); will-change: transform, backdrop-filter`), (2) an invalid 4-value `contain-intrinsic-size` syntax on `.package-card` that caused older WebKitGTK versions to drop the rule and collapse `content-visibility` elements to 0px height, creating massive scrollbar thrashing (fixed by using the older, safer syntax `contain-intrinsic-size: 180px; contain-intrinsic-height: 180px`), and (3) a `fadeInUp` CSS animation applied globally to all `.package-card` elements, forcing WebKit to maintain active animation states for thousands of nodes at once (fixed by removing the animation).
- **Dialog component icons (2026-06-01):** the confirm-modal checkbox/radio options (optdep
  list, missing-deps, AUR provider choice) now show their source/repo/AUR icons. The gem
  `InputOption.icon_path` (an on-disk SVG) is inlined as a base64 data URI in
  `_serialize_option` (`watcher._icon_data_uri`, cached) and rendered as a small `<img>` in
  `main.js`. Combo selects keep text only (native `<option>` can't show images). Tests in
  `test_watcher.py`.
- **Rust (`atlas_rs`) dropped — Atlas is pure-Python (2026-06-01):** removed the native
  extension entirely (`rust/` crate, the built `.so`, `gems/arch/native.py`, `test_native.py`,
  setuptools-rust from `setup.py`/`pyproject.toml`). `srcinfo.map_srcinfo` is now the sole
  (pure-Python) parser. Atlas builds with a plain `pip install -e .` — no cargo, no `.so`.
  Verdict: a package manager is I/O-bound, so native code didn't earn its keep (only
  `map_srcinfo` was ever CPU-bound, and imperceptibly so). Also pointed the app's data fetch
  at `atlas-files@main` and de-Qt'd the app (no PyQt5). Docs updated (AGENTS/ARCHITECTURE/
  ROADMAP/DEVELOPMENT reflect pure-Python; `atlas_rs-API.md` deleted). Refreshed stale Python
  classifiers (3.6–3.8 → 3.9–3.13).
- **Rebrand-leftover sweep (2026-06-01):** removed the runtime/packaging `bauh` leftovers —
  `.desktop` `Name`/`Exec=/usr/bin/bauh`→`atlas` + `Icon=atlas`; deleted the dead
  `atlas_tray.desktop` (tray was purged, `atlas-tray` exec gone); `[bauh]` console log
  prefixes → `[atlas]` (util/appimage/web); generated-file identifiers (`bauh_appimage_*`
  desktop entries → `atlas_appimage_*` via the shared `_gen_desktop_entry_path`;
  `bauh_scaling_governor` temp → `atlas_scaling_governor`; makepkg marker
  `# <generated by bauh>` → `atlas`); stale docstrings; AppImage update-info owner
  `vinifmor` → `Vatteck`. Code + packaging are now bauh-free (`grep` clean) and the English
  locale has no `bauh`. **Left intentionally:** non-English locale translations (separate
  i18n surface, not shown in the default UI) and docs/plans (legitimately say "formerly
  bauh"). Note: renaming the AppImage desktop-entry prefix orphans any entry a prior bauh
  install made — none exist here (no AppImages installed).
- **Desktop notifications wired up (2026-06-01):** `notify_user` existed and `notify-send`
  is present, but nothing called it and the `system.notifications` flag controlled nothing.
  `AtlasApi._notify(msg)` now fires a desktop notification on finished install / uninstall /
  update / batch-uninstall / update-all, gated on `core_config['system']['notifications']`
  (the Settings toggle now does something). Failures are swallowed so a notification can
  never break an operation. Tests: `tests/view/webview/test_api.py::NotifyTest`.
- **Webview Settings page (focused) (2026-06-01):** the Settings nav was a placeholder with
  no backend — so re-enabling a gem we'd disabled by default was impossible. Built a
  focused, **webview-native** page (not the Qt-era `GenericSettingsManager.get_settings`
  tree, which imports PyQt5 + shows Qt-only options): `AtlasApi.get_app_settings` /
  `save_app_settings` talk straight to the config managers. Covers **package-type
  enable/disable** (writes `core_config['gems']` + live `set_enabled`, so it applies without
  restart; types that can't work show disabled), **Flatpak install level**, and general
  toggles (suggestions / notifications / ask-reboot / download icons / store root password).
  `main.js` `renderSettings()`/`saveSettings()`. Tests:
  `tests/view/webview/test_api.py::AppSettingsTest`. Plan:
  [plans/2026-06-01-webview-settings.md](plans/2026-06-01-webview-settings.md).
- **Multi-source app cards — Phase 2a (2026-06-01):** the same app offered by more than one
  source is now one card with a source switcher. `main.js` `collapseByName()` groups the
  (already-ranked) list by exact normalized name; within a group sources sort installed-first
  then `arch_repo → aur → flatpak → appimage` (`compareSourcePreference`). Multi-source cards
  render clickable `.source-pill`s (AUR amber) instead of the plain tag; clicking re-renders
  the card body for that source (`cardInnerHTML`) and re-targets `data-id`, so Install/
  Uninstall/Update/pin/detail all act on the selected source. Single-source cards are
  unchanged (keep the phase-2b AUR badge). Different *names* stay separate, so AUR
  `-bin`/`-git` variants and forks remain their own cards. Verified grouping: an installed
  Arch app + its AUR/Flatpak siblings collapse with the installed (Arch) source default.
- **Search-result declutter (2026-06-01):** four tweaks in `main.js`/`style.css` —
  (1) **letter-avatar fallback icons** (`letterAvatar()`): icon-less packages (most
  AUR/repo) now get a colored initial keyed to the source instead of identical gray
  squares; (2) **condensed AUR badge** — the three pills collapsed into one
  `AUR · source · ▲81` (out-of-date stays a separate red flag); (3) **name-match ranking**
  for search (`sortByRelevance()`: exact > prefix > name-contains > description-only), so
  description-only matches sink; (4) **tighter grid** (300px min cols, smaller gaps/padding,
  full-bleed icons). Note: most "duplicate-looking" search results are genuinely *different*
  packages, so Phase 2a grouping won't dedupe them — this was the actual fix.
- **AUR variants ranked + badged — Phase 2b (2026-06-01):** AUR ships base/`-bin`/`-git`
  etc. as distinct packages; they stay separate cards (different build choices) but are now
  legible. `_serialize_pkg` exposes `votes`/`popularity`/`maintainer`/`out_of_date`/
  `package_base` (None for non-Arch). `main.js` derives the build kind from the name suffix
  (`aurVariant()` → source/binary/git/debug, plus the stripped **base name** so future
  grouping is render-only), badges each AUR card, and ranks AUR results among themselves
  (`rankAur()`: installed → non-VCS → not-out-of-date → votes desc; **VCS never first**)
  without disturbing non-AUR ordering. Verified ranking: bin → source → out-of-date → git.
  Decision to keep them ungrouped (not merged under one card) is in the plan doc.
- **Source-type filter rework — Phase 1 (2026-06-01):** the type filter was decorative
  (`pkg_type` was passed to the backend but ignored, and nothing filtered client-side).
  Atlas is now Arch-focused: Snap/Debian/Web gems are **off by default**
  (`is_default_enabled() → False`; still re-enableable in Settings — `_can_work` gates every
  op on `is_enabled()`), and the filter lists exactly **Arch / AUR / Flatpak / AppImage**.
  Filtering is now real + client-side (`normalizeType` + `filterByType` in `main.js`): the
  full set is fetched once and the dropdown narrows it instantly (cache key is now
  type-independent). Card tags show friendly labels; **AUR is visually distinct** (amber +
  ⚠ + "less vetted" tooltip) from the trusted official-repo tag. Arch and AUR are always
  separate. Tests: `tests/gems/test_default_enabled.py`. **Phase 2 (merge multi-source apps
  into one card with a source switcher) is still pending** — see
  [plans/2026-06-01-source-types-and-multisource-cards.md](plans/2026-06-01-source-types-and-multisource-cards.md).
- **Config merge no longer wiped structured defaults with a null override (2026-06-01):**
  `commons/util.deep_update` set `source[key] = None` when a cached/partial config had a
  nested block as null, clobbering the default dict. Callers then did `config['block']
  ['key']` → `TypeError: 'NoneType' object is not subscriptable` (seen as the AppImage
  `suggestions.expiration` ERROR+traceback at startup). Now a `None` override is ignored
  when the default at that key is a dict (and the recursion tolerates a `None` default
  being overridden by a dict). Affects **all** gem configs via `YAMLConfigManager.get_config`.
  Tests: `tests/common/test_util.py::DeepUpdateTest`.
- **Flathub API v1 → v2 migration (2026-06-01):** Flathub retired the v1 REST API
  (`/api/v1/apps/{id}` → **404**), so Flatpak suggestion enrichment, the info panel and
  screenshots all failed (log spam: `Could not retrieve app data … Server response: ?`).
  Migrated to the v2 AppStream API behind a new `atlas/gems/flatpak/flathub.py` (the only
  module that knows the v2 endpoints/shape). Mapping highlights: `icon` is now an absolute
  URL; `categories` is a list of strings (was `[{name}]`); version/notes/date live under
  `releases[0]`; screenshots are `sizes[].src` (pick widest). Three callers updated
  (`worker.py`, `controller.get_info`, `controller.get_screenshots`). Pure mappers are
  unit-tested against a captured payload (`tests/gems/flatpak/test_flathub.py` +
  `resources/flathub_v2_appstream_gimp.json`). Plan:
  [plans/2026-06-01-flathub-v2-api-migration.md](plans/2026-06-01-flathub-v2-api-migration.md).
  Apps not on Flathub (installed from other remotes) now 404 **quietly**: `get_appstream`
  uses `single_call=True` (one request, no retry, no http-layer WARNING) and logs the miss
  at DEBUG — no more WARNING spam for e.g. `com.ml4w.*`, `com.nvidia.geforcenow`.
- **Confirm modal now renders input components (2026-06-01):** installing e.g. `gimp`
  showed the optdep prompt and the missing-deps prompt but **no list** — the modal only
  rendered title/body text. The confirm modal now renders checkbox lists, single-select
  radios/combos and forms, and round-trips the selections back into the gem's component
  objects (watcher `_serialize_components`/`_apply_selections`, JS `renderConfirmComponents`
  + `submit_confirmation(confirmed, selections)`). Fixes optdep selection, missing-deps
  display, and AUR provider choice. Tests: `tests/view/webview/test_watcher.py`.
- **Arch install reported "failed" though the package installed (2026-06-01):** installing
  e.g. `gimp` ran pacman successfully but the op reported **failed**. Two independent bugs,
  both fixed:
  1. **Root cause (the crash):** `pacman.map_update_sizes`/`map_download_sizes`/
     `get_installed_size` paired regex size-matches to the requested package names
     *positionally* (`pkgs[idx]` over `enumerate(RE.findall(output))`). `pacman -Si <names>`
     prints one block **per matching package**, so a package present in >1 enabled repo
     (e.g. `extra` + `extra-testing`) yields more size lines than names → `IndexError`
     (gimp's 7 repo optdeps produced 12 size lines). Fixed by parsing per-package blocks and
     mapping each block's `Name` → size (`_map_pkg_sizes`). Tests in `test_pacman.py`.
  2. **Defense in depth:** `_install_from_repository`/`_install_from_aur` returned the
     *optdep* step's result as the whole-install result, so any optdep failure/cancellation
     flipped an already-successful main install to "failed". Optdeps are optional — both
     paths now run them in a `try/except` and always return the main package's result
     (matching the code's own `# because the main package installation was successful`).
     Tests in `test_install_optdeps.py`.
- **All watcher dialogs are now HTML modals (2026-05-30):** converted
  `request_confirmation`/`request_reboot`/`show_message` off the dead
  `window.confirm`/`alert` to blocking HTML modals (`#confirm-modal`, `#message-modal` +
  `showConfirmModal`/`showMessageModal` in `main.js`), mirroring the password modal.
  AtlasApi gained `prompt_confirmation`/`prompt_message` + `submit_confirmation`/
  `submit_message_ack` callbacks; the watcher delegates and strips HTML from gem text via
  `_clean()`. Caveat: rich `components` aren't rendered (text only). 4 new tests.
- **Root-password flow for the webview (2026-05-30):** `api.py` passed
  `root_password=None` to every privileged op → Arch/AUR installs ran unprivileged and
  failed. Added a session-scoped broker on `AtlasApi` (`acquire_root_password` /
  `ensure_root_password` / `submit_root_password`) + an HTML password modal
  (`#password-modal` in `index.html`, `showPasswordModal` in `main.js`) replacing the
  broken `window.prompt` path, plus `validate_root_password()` in `commons/system.py`
  (`sudo -k -S -v`). Wired into install/uninstall/update/update_all/batch_uninstall/
  import; `WebviewWatcher` now delegates `request_root_password` to the broker. 3 new
  tests in `test_api.py`. **Needs GUI verification (can't be driven headless).**
- Rebrand bauh → Atlas (namespaces, config paths `~/.config/atlaspm` etc., UI strings).
- Qt5 UI purged; pywebview front-end (`atlas/view/webview/`) in place.
- `atlas_rs` build pipeline (PyO3 + setuptools-rust, `debug=False`), installed at
  `atlas.gems.arch.atlas_rs`. Crate is now `lib.rs` only; deps trimmed to just `pyo3`
  (`.so` ~621 KB, down from 3.6 MB).
- `map_srcinfo` — native `.SRCINFO`/pacman field parser (~2×), with a Python fallback
  in `srcinfo.py`. **The only surviving native function.**
- **Native dependency resolver removed** (`resolver.rs`/`aur.rs`/`pacman.rs`/`sys.rs` +
  `map_missing_deps`): I/O+UI-bound, not a useful Rust target (2026-05-29).
- Documentation set: ARCHITECTURE, ROADMAP, DEVELOPMENT, atlas_rs-API; cross-agent
  onboarding (AGENTS.md / CLAUDE.md / GEMINI.md) + this baton.
- **Phase 0 complete:** boundary instrumentation (`native.py` switches), `deps_data`
  schema fix, benchmark harness (`benchmarks/bench_srcinfo.py`), and the release-build
  fix (`setup.py debug=False`).
- **Native import fix (critical):** `native.load()` imported bare `atlas_rs`, which never
  resolves at runtime → the native path was dormant in production. Now imports
  `from atlas.gems.arch import atlas_rs`.
- **Native pacman info parser: tried then reverted.** Wired into `map_updates_data` and
  parity-tested, but only ~1.2× (marshalling-bound), so reverted to cut maintenance.
  Kept the clean `_parse_info_output_py` extraction (+ its correctness test). Lesson
  recorded in `benchmarks/README.md` and the roadmap.
- **map_srcinfo fallback restored** (`atlas/gems/arch/srcinfo.py`): native-first via
  `native.load()` with the original pure-Python parser as fallback; `aur.py` now imports
  from there. Closes the last native path with no fallback. Parity-tested (incl. `fields`).
- **Native resolver retired** (2026-05-29): removed the 4 dead Rust modules +
  `map_missing_deps` and trimmed Cargo deps. `map_srcinfo` still passes; full suite green.
- Full Python suite 183 — all green. (cargo test: 0 — `map_srcinfo` is covered by the
  Python parity test `test_srcinfo.py`.)

---

## Known gaps / gotchas (don't get burned)

- **Mirror refresh is Manjaro-only / dead on Arch (2026-06-02).** `pacman.refresh_mirrors()` runs
  `pacman-mirrors -g` — a **Manjaro** tool, not present on Arch/CachyOS (which use
  `reflector`/`rate-mirrors`/`cachyos-rate-mirrors`). So `ArchManager.refresh_mirrors` can't work on
  the target platform; it's a bauh/Manjaro leftover. Fix proposed in
  [plans/2026-06-02-arch-mirror-refresh.md](plans/2026-06-02-arch-mirror-refresh.md) (detect the real
  Arch tools). Until then, regenerate mirrors manually with `reflector`.
- **Never call `window.evaluate_js` on the GTK main thread (2026-06-02).** pywebview's
  `evaluate_js` blocks the calling thread on a semaphore that's only released by a callback the
  **GTK main loop** runs — so calling it from the main thread (e.g. inside a `GLib.idle_add`
  callback, a GTK signal handler, or an AppIndicator menu `activate`) deadlocks the whole UI
  ("application not responding", though the process is alive). Call it from a worker/background
  thread instead. This bit the tray twice; the tray now pushes to JS only from its poller thread
  and runs menu-triggered navigation on a short daemon thread.
- **AppIndicator custom icons on KDE need an absolute path, not a theme name (2026-06-02).**
  `set_icon_theme_path(dir)` + `set_icon_full('name')` does **not** resolve on KDE's SNI host
  (you get the "A" letter-avatar). Pass an **absolute file path** to `set_icon_full` so the lib
  sends pixmap data. The tray's dynamic count badge relies on this; the un-badged/zero state uses
  the installed themed name (`atlas-pm`, in hicolor) which does work.
- **System tray (2026-06-02):** built on **AppIndicator/SNI** (`atlas/view/tray.py`), so it
  shows on **KDE Plasma natively** but **GNOME needs the AppIndicator extension** (desktop-side,
  not our bug — don't try to work around it). Two more notes: (1) `gi`/AppIndicator are **not
  in the project venv** — the GUI (and thus the tray) runs under **system Python**; `TRAY_AVAILABLE`
  is False inside the venv, which is why tray *logic* is unit-tested but the indicator itself is
  GUI-eyeball-only. (2) libayatana prints a harmless `…is deprecated, use libayatana-appindicator-glib`
  warning at startup; ignore it (a future polish could switch namespaces). Close-to-tray is
  **opt-in** via `ui.tray.minimize_to_tray` (default off) so closing still quits by default.
- **WebKitGTK has no `window.prompt`/`confirm`/`alert`.** They return `null`/no-op, so the
  watcher's old `evaluate_js("window.prompt/confirm/alert(...)")` never worked. **All four
  are now HTML modals** (password, confirm, message) that block the worker thread on a
  `threading.Event` and resolve via `js_api` callbacks (`submit_root_password`,
  `submit_confirmation`, `submit_message_ack`). Never reintroduce a `window.*` dialog.
- **`request_confirmation` renders input components (2026-06-01).** The confirm modal now
  renders `MultipleSelectComponent` (checkbox list), `SingleSelectComponent` (radio or
  combo), `FormComponent`, and `TextComponent`, and returns the user's selections. The
  watcher serializes the component tree (`_serialize_components`) and applies the returned
  option-index selections back onto the original objects (`_apply_selections`) so arch's
  `request_optional_deps` / `confirm_missing_deps` / `request_providers` read the choices
  as before. Covered by `tests/view/webview/test_watcher.py`. Not yet rendered: option
  icons (decorative; repo/aur svgs are skipped) and component types outside the four above
  (none are used in confirmation flows today).
- **Root password requires the GUI to drive it; can't verify headless.** The broker shows
  a modal and blocks a pywebview worker thread on a `threading.Event`. Relies on pywebview
  dispatching each `js_api` call on its own thread (true for the GTK backend). User must
  confirm install/cancel/wrong-password behaviour in the running GUI.

- **Tray mode is gone (was broken).** The rebrand purged Qt but left `tray.py`/`manage.py`
  importing the deleted `atlas.view.qt.*` — `atlas-tray` crashed on launch. Removed them +
  the `atlas-tray` entry point + `--tray` arg + `context.new_qt_application`/`set_theme`
  (2026-05-29). README roadmap notes a non-Qt tray could be reintroduced.
- ~~**Residual PyQt5 coupling**~~ **Removed (2026-06-01).** The webview app no longer
  imports PyQt5: dropped the Qt HDPI block in `app.py`; de-Qt'd `view/util/util.py`
  (`get_default_icon`→`get_default_icon_path`; `restart_app` now stops the pywebview/GTK
  loop via `webview.windows[*].destroy()` instead of `QCoreApplication.exit()`); removed
  the Qt widget-style selector + `QApplication`/`QStyleFactory` import from
  `view/core/settings.py`; swapped `pyqt5` → `pywebview` in `pyproject.toml` deps (matching
  requirements.txt). **Verified** by importing `atlas.app` and `atlas.cli.app` with PyQt5
  forced-absent (`sys.modules['PyQt5']=None`). Leftovers (harmless, not Qt imports): a
  commented `QApplication` line in the unused `stylesheet.py`, and the now-unused
  `ui.qt_style`/`hdpi`/`scale_factor` config keys (read only by the dead, webview-unreachable
  `GenericSettingsManager.get_settings` path).
- **App run-status:** ✅ GUI confirmed working (user launched `python -m atlas.app` on
  2026-05-29 — window loads, lazy gem init fires, background prepare ~10ms, suggestions
  run). Remaining log noise is expected: first-run (no cache/db), no-root (`pacman -Sy`
  can't sync), harmless pywebview GTK `window.native.*` warnings, and `atlas-files`
  download failures.
- ~~**`atlas-files` repo content.**~~ Resolved: `github.com/Vatteck/atlas-files` exists
  (cloned from `bauh-files`) and **all 10 download paths return 200** (verified
  2026-05-29, both `master` and `main` serve content). Content is package-manager-
  agnostic with no `bauh`/`vinifmor` self-references, so it works for Atlas as-is. The
  earlier launch-log download failures were just timing (predated the repo).
  Suggestion lists curated for Arch (2026-06-01, **pushed** to `atlas-files@main`): arch +=
  firefox/mpv/keepassxc and mangohud moved out of aur (it's in extra); appimage −
  yuzu/citra-nightly (shut down). Names verified via `pacman -Si`. Also pointed the app at
  the `atlas-files` **`main`** branch (was `master`; deleted the redundant remote master) —
  single source of truth. To see new suggestions immediately: `rm ~/.cache/atlaspm/*/suggestions.*`.
  **AUR suggestions now work (2026-06-01):** `list_suggestions` resolves suggestion names not
  in the official repos via the AUR RPC (`aur_client.get_info`, one batched call, gated on
  `aur.is_supported`), so AUR apps can be suggested. `arch/suggestions.txt` now holds repo +
  AUR names (the curated AUR picks were merged in; `aur/suggestions.txt` stays unused legacy).
  Tests: `tests/gems/arch/test_suggestions_aur.py`. Plan:
  [plans/2026-06-01-aur-suggestions.md](plans/2026-06-01-aur-suggestions.md).

- ~~**Silent fallback hides Rust bugs.**~~ Addressed: native calls now go through
  `atlas/gems/arch/native.py`; run with `ATLAS_RS_DEBUG=1` to log native failures, or
  `ATLAS_DISABLE_RS=1` to force the Python path. (Default behaviour still falls back
  silently.)
- ~~**`map_srcinfo` had no Python fallback.**~~ Fixed: `atlas/gems/arch/srcinfo.py`
  wraps native with the original Python parser; a missing `.so` no longer breaks the
  Arch gem at import. (Native and Python verified to agree, including `fields` cases.)
- **Don't re-attempt a native dependency resolver.** Removed 2026-05-29. The Python
  `map_missing_deps` is I/O-bound (pacman/AUR), recursive, and UI-coupled (watcher
  provider choices) — not CPU. A native port needs Rust→Python callbacks and isn't
  faster. The prototype also re-derived everything, ignoring caller context.
- **Lesson — only port CPU-bound ops with small results.** The native pacman info parser
  measured only ~1.2× (PyO3 result-marshalling + list→set conversion dominate when
  returning many dicts) and was reverted; the resolver was I/O-bound. `map_srcinfo`
  (~2×, one compact dict) is the shape that works. Weigh CPU-vs-I/O and result size
  before any new native path.
- ~~**Rust build/debug gotchas.**~~ Obsolete — the Rust extension was removed (2026-06-01);
  Atlas builds with a plain `pip install -e .`, no cargo.
- Large Python files to read in sections, not whole: `controller.py` (~192 KB),
  `updates.py` (~42 KB), `pacman.py` (~38 KB).

---

## Decision log (append-only; newest first)

- **2026-06-01** — Fixed severe scroll lag in the package grid. Root causes were (1) the sticky `.topbar` with `backdrop-filter: blur(16px)` overlapping the scrolling packages grid, forcing expensive repaints (fixed by promoting to a compositor layer via `transform: translateZ(0); will-change: transform, backdrop-filter`), (2) an invalid 4-value `contain-intrinsic-size` syntax on `.package-card` that caused older WebKitGTK versions to drop the rule and collapse `content-visibility` elements to 0px height, creating massive scrollbar thrashing (fixed by using the older, safer syntax `contain-intrinsic-size: 180px; contain-intrinsic-height: 180px`), and (3) a `fadeInUp` CSS animation applied globally to all `.package-card` elements, forcing WebKit to maintain active animation states for thousands of nodes at once (fixed by removing the animation).
- **2026-05-30** — Converted the remaining `window.confirm`/`alert` watcher dialogs
  (`request_confirmation`/`request_reboot`/`show_message`) to blocking HTML modals, reusing
  the password-broker pattern (evaluate_js → worker blocks on Event → `js_api` callback
  resolves). Rich `components` are intentionally not rendered yet (text only). Same root
  cause as the password fix: WebKitGTK has no native JS dialogs.
- **2026-05-30** — Fixed Arch/AUR "no root access" installs. Root cause: `api.py`
  hardcoded `root_password=None` and the only prompt path used `window.prompt` (dead in
  WebKitGTK). Added a session-cached root-password broker on `AtlasApi` + HTML modal +
  `validate_root_password` (`sudo -k -S -v`), wired into all privileged ops, and pointed
  `WebviewWatcher.request_root_password` at the broker. Design:
  `plans/2026-05-30-root-password-flow-design.md`. Awaiting GUI verification.
- **2026-05-29** — GUI confirmed working end-to-end. Fixed 6 rebrand-leftover URLs still
  pointing at `vinifmor/...` (→ `Vatteck/...`): appimage dbs, arch categories + gpg
  servers, appimage app repo, setup.py + pyproject repository URL.
- **2026-05-29** — Ran the app for the first time; found `atlas-tray` broken (dead Qt
  imports the rebrand purge missed). Removed the broken tray + orphaned `manage.py` +
  `new_qt_application`/`set_theme` + the `atlas-tray` entry point and `--tray` arg.
  `context.py` no longer needs PyQt5. README/STATUS updated; tray reintro is roadmapped.
- **2026-05-29** — Retired the native dependency resolver: removed `resolver.rs`,
  `aur.rs`, `pacman.rs`, `sys.rs`, the `map_missing_deps` PyO3 fn, and the `serde`/
  `serde_json`/`ureq`/`regex` deps. Reason: I/O+UI-bound, not a viable Rust target (a
  faithful drop-in needs Rust→Python callbacks for pacman/AUR/watcher and wouldn't be
  faster). `lib.rs` is now `map_srcinfo` only; `.so` 3.6 MB → 621 KB. Migration verdict:
  port only CPU-bound ops with small results. Pivoting to Python-side startup wins.
- **2026-05-29** — Reverted the native pacman info parser (~1.2×, marshalling-bound) to
  cut maintenance surface; kept the `_parse_info_output_py` extraction + test. Confirms
  the rule: only port parsers with small results.
- **2026-05-29** — Restored a Python fallback for `map_srcinfo` (`srcinfo.py`); it was the
  only native function with none, so a missing `.so` would have broken the Arch gem.
  Native↔Python parity verified (incl. `fields`).
- **2026-05-29** — Wired native pacman `-Si` parser into `map_updates_data` (parity-tested,
  ~1.2×). Fixed the critical dormant-native import bug (bare `import atlas_rs` never
  resolved). Disabled the non-faithful native `map_missing_deps`. Chose the pacman-parser
  task after finding version-compare is NOT the update hot path (pacman -Qu does repo
  comparison; per-call vercmp across PyO3 would be slower than Python).
- **2026-05-28** — Phase 0 closed with a benchmark (`benchmarks/bench_srcinfo.py`). It
  revealed `pip install -e .` shipped a *debug* `atlas_rs` (~4× slower than Python);
  pinned `setup.py debug=False` → release builds, native now ~2× faster. Lesson encoded:
  always measure release builds.
- **2026-05-28** — Fixed native `deps_data` schema: Rust emits canonical short keys via
  per-source `to_deps_data()`; pacman.rs parses Description/Download/Installed sizes.
  Rust tests 4→13; verified end-to-end on a real package. Plans under `docs/plans/`.
- **2026-05-28** — Phase 0 instrumentation: all native (`atlas_rs`) calls route through
  `atlas/gems/arch/native.py` with `ATLAS_RS_DEBUG` / `ATLAS_DISABLE_RS` switches.
  Default still falls back silently; switches add visibility + an escape hatch.
- **2026-05-28** — Adopted AGENTS.md as the single canonical agent manual; CLAUDE.md and
  GEMINI.md are thin redirects to avoid drift across Claude/Codex/Gemini.
- **2026-05-28** — Migration strategy fixed as **strangler-fig, hot paths first**: Rust
  added behind Python fallbacks, fallback removed only after the native path is proven.
- **2026-05-28** — Python↔Rust boundary is **coarse-grained**: one whole task per call,
  no Rust→Python callbacks (rationale in ARCHITECTURE §3).

---

## Template for a STATUS update (copy when editing)

```
**Last updated:** YYYY-MM-DD
- Moved <item> from Next → Done.
- New Current focus: <…>. New Next: <…>.
- New gotcha discovered: <…> (and where it lives).
- Decision: <what + why>.
```
