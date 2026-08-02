# STATUS — the handoff baton

> **The single most important file for cross-agent continuity** — the live state of the
> project. Read it at the start of every session; update it at the end of every session that
> changes code (AGENTS.md §7).
>
> **Keep this file short.** It is a baton, not a ledger. When an entry stops being live,
> move it to [HISTORY.md](HISTORY.md) (the full shipped record) or delete it. If this file
> passes ~200 lines, it has stopped doing its job — archive again.

**Last updated:** 2026-08-01
**Version:** 0.16.1 (released 2026-07-18, tag `v0.16.1`, release commit `c8b9c37`; CI
auto-published to the AUR). Both AUR packages live: stable **`atlas-pm`** + bleeding-edge
**`atlas-pm-git`**.
**Branch:** `master` (= `origin/master`). Always run `git branch` rather than trusting this line.
**Health:** 774 Python tests + 60 JS contract tests green; CI green across Python 3.10–3.14.

> Feature wishlist lives in **[BACKLOG.md](BACKLOG.md)**. Everything already shipped is in
> **[HISTORY.md](HISTORY.md)** and **[CHANGELOG.md](../CHANGELOG.md)** — don't re-read those to
> start work, just search them.

---

## Current focus

**0.17 — "verify and show," not "add" (started 2026-08-01).**

The feature backlog is drained and BACKLOG's north star is met, so the next phase is not more
features. Two things drive it:

1. **Almost every GUI eyeball finds a real defect the 774-test suite cannot** — the undefined
   `--color-success` that silently killed the dependency tree's colors, the full-bleed Updates
   banner, the stranded-scroll blank page (no JS error, no log line), the mirrorlist row shouting
   in red after every action on it became safe. The suite is fast and green and structurally blind
   to render-level bugs.
2. **The public face is stale.** Atlas is published on the AUR at 0.16.1, but the README
   screenshots are from 2026-06-02 — they predate themes/accents, the floating terminal + log
   highlighting, the dependency tree, the calmed `.pacnew` center, and the PKGBUILD reader.

Step 1 (doc/repo debt) is done — see Done below. Steps 2–3 are in Next.

## Next

1. ~~**GUI eyeball — the one outstanding item.**~~ ✅ **CLEARED 2026-08-01 by Vatteck.** 0.16.1's
   PKGBUILD inline reader in the pre-build review modal (which shipped and released without ever
   being looked at), plus the boot splash and theme-preset/accent contrast, were all walked on the
   real desktop and confirmed good. **Nothing is currently awaiting a GUI eyeball.**
2. **Refresh the screenshots.** All five `docs/screenshots/*.png` are from 2026-06-02 and predate
   themes/accents, the floating terminal + log highlighting, the dependency tree, the calmed
   `.pacnew` center, and the PKGBUILD reader. `terminal.png` especially — it still shows the
   flat-green sidepane, which no longer exists.

   **Tooling is ready:** `tools/capture-screenshots.sh` (DEVELOPMENT.md §8). Start Atlas, run it,
   navigate to each view and press Enter — it floats/sizes the window to a consistent 1280×800,
   raises it so nothing overlaps, squares off Hyprland's rounded corners, crops to the window rect
   and writes to `docs/screenshots/`. Needs a GUI session, so it's Vatteck's to run.

   *Deliberately not automated with a headless browser:* the UI would run (there's a clean
   `pyApiCall` seam with a `mockApi` fallback), but Chromium is not WebKitGTK and Atlas's bug
   history is full of WebKit-specific rendering failures — README images from an engine no user
   runs would be a subtle lie. Fixture-driven headless rendering belongs in Next #3, where its
   value is regression testing, not marketing images. *(The repo description and issue template
   halves of this step are done — see Done.)*
3. **Then pick a real engineering thread** with fresh eyes. Leading candidate: a **render-level test
   harness** for the `main.js` view renderers, since that is exactly where every recent defect lived
   and where the current tests are blind. Alternative: the paused cold-start work below.

### Paused thread — startup memory

Measured and partly fixed; **do not restart the measurement work**, it is all in
[plans/2026-07-17-memory-baseline.md](plans/2026-07-17-memory-baseline.md).

- Whole app is ~400–460 MB PSS. An *empty* pywebview window already costs ~200 MB — that is the
  architecture floor, not an Atlas bug.
- **Fixed:** `pacman.map_desktop_files` buffered `pacman -Ql <every package>` as one string during
  first-run cache warm-up. Now streamed — **cold peak 528.7 → 451.7 MB measured.**
- **Shipped as a cheap guard, no measured delta:** in-flight coalescing of concurrent full
  `read_installed` calls (leader/follower; `ATLAS_NO_READ_COALESCING=1` kills it).
  [plans/2026-07-17-coalesce-read-installed.md](plans/2026-07-17-coalesce-read-installed.md).
- **Remaining is structural:** the GUI's arch read waits on the pre-cacher's disk-cache task while
  the pre-cacher runs its own read as that cache's data source. Merging them is an arch-gem redesign
  with circular-wait risk — **needs its own plan before any code.** Modest ceiling given the ~200 MB
  floor.
- **Measured dead ends, don't re-try:** tracemalloc inflates RSS ~3×, `MALLOC_ARENA_MAX=2` made it
  *worse*, `malloc_trim` reclaims ~1 MB.

## Done (recent)

Full record in [HISTORY.md](HISTORY.md). Only the last few entries live here.

- **Doc + repo debt cut (2026-08-01).** Re-entry after a 2-week gap cost more than the work would
  have: STATUS.md had reached **2,379 lines / 94 KB** and no longer fit in an agent's read budget.
  Split into this baton + [HISTORY.md](HISTORY.md) (the Done log, retired gotchas, and the
  Rust/Qt-era decision log). Also deleted two fully-merged dead branches
  (`feat/webview-polish-sprint-1`, `-2`; 0 commits ahead of master) and ~122 MB of regenerable
  `makepkg` artifacts under `linux_dist/arch/`. **Fixed a real doc bug found while measuring:** the
  large-files gotcha named `view/core/controller.py` at "~192 KB" — it is actually **32 KB**; the
  220 KB file is `gems/arch/controller.py`, and the two genuinely largest files (`main.js` 340 KB,
  `api.py` 184 KB) were not listed at all. Corrected here and in AGENTS.md §8. No app-code change;
  suite unaffected (774 + 60).
- **Public-face cleanup (2026-08-01).** Added a **bug-report issue template** (`.github/ISSUE_TEMPLATE/`)
  — issues were enabled with no template, so reports arrived without the two things that make an
  Atlas bug diagnosable: `~/.cache/atlaspm/logs/atlas.log` and `atlas --self-check` output. The form
  front-loads both, plus install source, distribution (derivatives change mirrorlist/update
  behaviour), and package source; `config.yml` points feature ideas at BACKLOG's non-goals and
  redirects "this AUR package is malicious" to the AUR while keeping audit false positives/negatives
  on-topic. Also **fixed the GitHub repo description**, which led with "AppImage, Arch/AUR, Flatpak,
  Snap, Web" — burying Arch and advertising three sources that are off by default — and **deleted
  three fully-merged remote branches** (`feat/webview-polish-sprint-2`, two `claude/*`; all 0 commits
  ahead of master). Screenshots are the remaining half of this step — see Next #2.
- **Read the PKGBUILD inside the pre-build review modal (2026-07-18).** The mid-Update-All "Review
  PKGBUILD" advisory dialog told the user to read the PKGBUILD while offering no way to. The
  `review` payload now carries the PKGBUILD + `.install` texts as `files: [{name, text, findings}]`
  and `renderPkgbuildReview` renders each as a collapsed, line-numbered, syntax-highlighted
  `<details>` reader. Suite 774 + JS 60. **GUI-verified by Vatteck 2026-08-01.**
- **Updates-banner gutters + dependency-tree rebuild (2026-07-17).** GUI-verified.
- **Terminal → centered dialog + log syntax highlighting (2026-07-17).** GUI-verified.
- **Compact Updates config-notice + friendlier `.pacnew` center (2026-07-17).** GUI-verified.

---

## Known gaps / gotchas (don't get burned)

Live traps only. Retired ones are in [HISTORY.md](HISTORY.md#retired-gotchas-resolved-or-obsolete--kept-so-they-arent-re-derived).

- **WebKitGTK has no `window.prompt`/`confirm`/`alert`.** They return `null`/no-op. **All dialogs
  are HTML modals** that block a pywebview worker thread on a `threading.Event` and resolve via
  `js_api` callbacks (`submit_root_password`, `submit_confirmation`, `submit_message_ack`). Never
  reintroduce a `window.*` dialog.
- **Never call `window.evaluate_js` on the GTK main thread.** pywebview's `evaluate_js` blocks the
  calling thread on a semaphore only released by a callback the **GTK main loop** runs — calling it
  from the main thread (inside a `GLib.idle_add` callback, a GTK signal handler, or an AppIndicator
  menu `activate`) deadlocks the whole UI ("application not responding", process still alive). Call
  it from a worker thread. This bit the tray twice; the tray now pushes to JS only from its poller
  thread and runs menu-triggered navigation on a short daemon thread.
- **Root password requires the GUI to drive it; can't verify headless.** The broker shows a modal
  and blocks a pywebview worker thread on a `threading.Event`, relying on pywebview dispatching each
  `js_api` call on its own thread (true for the GTK backend). Install/cancel/wrong-password
  behaviour must be confirmed in the running GUI.
- **`request_confirmation` renders input components.** The confirm modal renders
  `MultipleSelectComponent`, `SingleSelectComponent`, `FormComponent` and `TextComponent` and
  returns the user's selections; the watcher serializes the component tree
  (`_serialize_components`) and applies returned option-index selections back onto the original
  objects (`_apply_selections`) so arch's `request_optional_deps` / `confirm_missing_deps` /
  `request_providers` read choices as before. Covered by `tests/view/webview/test_watcher.py`. Not
  rendered: option icons (decorative) and component types outside those four (unused in confirmation
  flows today).
- **System tray is AppIndicator/SNI** (`atlas/view/tray.py`) — native on KDE Plasma, but **GNOME
  needs the AppIndicator extension** (desktop-side, not our bug; don't work around it). `gi`/
  AppIndicator are **not in the project venv**, so the GUI and tray run under **system Python** and
  `TRAY_AVAILABLE` is False inside the venv — tray *logic* is unit-tested, the indicator itself is
  GUI-eyeball-only. libayatana prints a harmless `…use libayatana-appindicator-glib` deprecation
  warning at startup; ignore it. Close-to-tray is opt-in via `ui.tray.minimize_to_tray` (default
  off), so closing still quits by default.
- **AppIndicator custom icons on KDE need an absolute path, not a theme name.**
  `set_icon_theme_path(dir)` + `set_icon_full('name')` does **not** resolve on KDE's SNI host (you
  get the "A" letter-avatar). Pass an **absolute file path** to `set_icon_full` so the lib sends
  pixmap data. The tray's dynamic count badge relies on this; the un-badged state uses the installed
  themed name (`atlas-pm`, in hicolor), which does work.
- **`refresh_mirrors` is an inert Manjaro leftover — intentionally left.** `ArchManager.refresh_mirrors`
  / `pacman.refresh_mirrors` / `RefreshMirrors` use Manjaro's `pacman-mirrors -g`. On Arch/CachyOS this
  **never runs**: the custom action isn't surfaced in the webview at all, and the startup worker is
  double-gated off (`refresh_mirrors_startup` defaults off **and** `is_mirrors_available()` =
  `which pacman-mirrors`, absent on Arch). Superseded by the Arch-correct `regenerate_mirrorlist`
  (reflector/rate-mirrors, in Settings → Mirrors). **Decision 2026-06-03: leave it.** Removing it
  would refactor the startup DB-sync flow (`RefreshMirrors` feeds
  `SyncDatabases.should_sync(mirrors_refreshed, …)`) + the custom-action registry + i18n, for **zero
  runtime gain**. Not a bug; don't "fix" it.
- **Don't re-attempt a native dependency resolver, and only port CPU-bound ops with small results.**
  The Python `map_missing_deps` is I/O-bound (pacman/AUR), recursive, and UI-coupled (watcher
  provider choices) — a native port needs Rust→Python callbacks and isn't faster. Measured evidence:
  the native pacman info parser hit only ~1.2× (PyO3 result-marshalling dominates when returning many
  dicts) and was reverted; only `map_srcinfo` (~2×, one compact dict) had the right shape. Weigh
  CPU-vs-I/O **and result size** before any native path. (AGENTS.md §3.2 + ROADMAP.)
- **To see new `atlas-files` suggestions immediately:** `rm ~/.cache/atlaspm/*/suggestions.*`. The
  app reads the **`main`** branch of [Vatteck/atlas-files](https://github.com/Vatteck/atlas-files).
- **Debugging the GUI:** Atlas writes a persistent rotating log to `~/.cache/atlaspm/logs/atlas.log`
  on **every** run (`--logs` only adds terminal output). A fresh run is INFO-only, so any
  WARNING/ERROR there is worth a look. **But note:** the stranded-scroll blank-page bug threw *no*
  JS error and *no* log line — it was a CSS scroll-container issue found with the WebKit inspector
  (which `--logs` enables via pywebview `debug=True`). Reach for the inspector when the log is silent.
- **Large files — read in sections, not whole** (verified 2026-08-01):
  `atlas/view/webview/main.js` **340 KB**, `atlas/gems/arch/controller.py` **220 KB**,
  `atlas/view/webview/api.py` **184 KB**, `atlas/view/webview/style.css` **120 KB**,
  `atlas/gems/arch/pacman.py` 48 KB, `atlas/gems/arch/updates.py` 44 KB.
  *(`view/core/controller.py` is only 32 KB — older docs misidentified it as the 192 KB file.)*

---

## Decision log (append-only; newest first)

Pre-2026-06 entries (the Rust/Qt era) are archived in
[HISTORY.md](HISTORY.md#historical-decision-log-2026-05-28--2026-05-30--the-rustqt-era).

- **2026-08-01** — **Split STATUS.md; next phase is verification, not features.** The baton had
  grown to 2,379 lines and become the main cost of re-entering the project. Archived to HISTORY.md.
  Chose "verify and show" (GUI eyeball → screenshots/positioning → render-level test harness) over
  resuming the startup-memory thread, because every recent GUI eyeball found a real defect the test
  suite could not, while the memory work has a ~200 MB pywebview floor capping its payoff.
- **2026-06-17** — **Deferred remote signed audit rules-packs indefinitely (designed, not built).**
  The signing scheme is fully designed (plans/2026-06-17-audit-rules-pack-signing.md) but
  deliberately unimplemented: a remote rule feed is a permanent supply-chain surface to own (crypto
  dep, key rotation/revocation, signing tooling + CI) and the value is marginal for an *advisory*
  scanner, since Atlas ships as a fast-updating `-git` AUR package — new bundled rules already reach
  users on a normal update. The shipped local fail-closed loader covers the real need. Revisit only
  if Atlas moves to a slow-release channel; if so, PyNaCl behind a `verify_pack()` seam. Reflects the
  maintainer's priority (solo dev, side project) to avoid standing maintenance burden.
- **2026-06-17** — **Dropped PKGBUILD-audit structural rule #3 (source-host ≠ url-host) on measured
  evidence.** On a random live AUR sample, 45% of packages declaring both a `url=` and a remote
  `source=()` had no source host matching the url host (31% even at registrable-domain level), and
  every example was legitimate (homepage vs source repo, `*.github.io`→`github.com`, npm registry,
  vendor CDN, moved hosts). ~1-in-3 fire rate with ~all false positives = the alert-fatigue failure
  mode the maintenance plan warns against ("more rules ≠ safer"). No code shipped; recorded so it
  isn't rebuilt. First real payoff of `atlas-cli audit-scan`: **measure before adding a rule.**
- **2026-06-01** — **Fixed severe scroll lag in the package grid.** Three root causes: (1) the sticky
  `.topbar` with `backdrop-filter: blur(16px)` overlapping the scrolling grid forced expensive
  repaints (fixed by promoting to a compositor layer via `transform: translateZ(0); will-change:
  transform, backdrop-filter`); (2) an invalid 4-value `contain-intrinsic-size` on `.package-card`
  made older WebKitGTK drop the rule and collapse `content-visibility` elements to 0px height,
  thrashing the scrollbar (fixed with the safer `contain-intrinsic-size: 180px; contain-intrinsic-height:
  180px`); (3) a global `fadeInUp` animation on every `.package-card` forced WebKit to maintain
  active animation state for thousands of nodes (removed).

---

## Template for a STATUS update (copy when editing)

```
**Last updated:** YYYY-MM-DD
- Moved <item> from Next → Done (and older Done entries → HISTORY.md).
- New Current focus: <…>. New Next: <…>.
- New gotcha discovered: <…> (and where it lives).
- Decision: <what + why>.
```
