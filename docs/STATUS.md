# STATUS — the handoff baton

> **The single most important file for cross-agent continuity** — the live state of the
> project. Read it at the start of every session; update it at the end of every session that
> changes code (AGENTS.md §7).
>
> **Keep this file short.** It is a baton, not a ledger. When an entry stops being live,
> move it to [HISTORY.md](HISTORY.md) (the full shipped record) or delete it. If this file
> passes ~200 lines, it has stopped doing its job — archive again.

**Last updated:** 2026-09-05
**Version:** 0.16.1 (released 2026-07-18, tag `v0.16.1`, release commit `c8b9c37`; CI
auto-published to the AUR). Both AUR packages live: stable **`atlas-pm`** + bleeding-edge
**`atlas-pm-git`**. Next: **0.16.2** (upgrade-pipeline safety, plan
[2026-08-16-upgrade-pipeline-safety.md](plans/2026-08-16-upgrade-pipeline-safety.md), implemented, not yet released;
GUI holds surface follow-up also implemented — [2026-08-16-gui-upgrade-holds.md](plans/2026-08-16-gui-upgrade-holds.md);
update cancellation clarity + cross-workspace attention notifications implemented —
[2026-08-29-update-cancellation-clarity.md](plans/2026-08-29-update-cancellation-clarity.md),
[2026-08-29-operation-attention-notifications.md](plans/2026-08-29-operation-attention-notifications.md)).
**Branch:** `master` (= `origin/master`). Always run `git branch` rather than trusting this line.
**Health:** 822 Python tests + 62 JS contract tests green; CI green across Python 3.10–3.14.

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

- **Atlas no longer runs any command it builds through a shell (2026-09-05).** Widened from the
  search-box fix below after Vatteck green-lit it ("Atlas is all about security"). The audit found
  the same shape in the shared helpers, and one was worse than the search box:
  **`SimpleProcess` accepted `shell=True` and implemented it as `' '.join(cmd)`** — callers passed
  a correct argv list (`['pacman', '-S', pkgname, '--noconfirm']`) and the helper flattened it back
  into a shell line. That covered install/remove/upgrade under `sudo -S`, with package names,
  `--ignore=<pkg>` and `--assume-installed=<provider>` interpolated — and providers/deps are parsed
  out of **AUR PKGBUILD/`.SRCINFO` fields**, i.e. attacker-controlled text. `new_root_subprocess`
  had the same join. Every `shell=True` call site in the tree passed a proper argv list, so the
  parameter was **removed from both helpers** rather than defaulted off. It was also corrupting
  arguments: `upgrade_several`'s `--overwrite=*` was reaching the shell as a glob.
  Also: `execute()` now takes an argument list (its `pacman -Rc <name>`, `pacman -Qi <names>`,
  `mkdir "<path>"` — double quotes don't stop `$(...)` — `git log` and `flatpak update` callers are
  converted); **`flatpak.search` is fixed** (same GUI query, same severity, default-on source); all
  remaining `run_cmd` interpolation in pacman/flatpak/makepkg/api/controller is argv; `flatpak.run`,
  `snap.run`, `appimage.launch` and `rebuild_detector` are argv; and the dead
  `commons.system.notify_user` (an `os.system` `notify-send` line, no callers) is deleted.
  **`tests/test_no_shell_execution.py` fails the build on any new `shell=True`/`os.system`** outside
  a small allowlist — verified by introducing a violation. Plan:
  [2026-09-05-shell-free-execution.md](plans/2026-09-05-shell-free-execution.md). Suite now
  **822 Python + 62 JS**, and the converted commands were smoke-tested against the real pacman,
  flatpak, git, find, diff, vercmp and systemctl.
- **The search box no longer reaches a shell (2026-09-05).** `pacman.search()` built a command
  line by concatenation (`'pacman -Ss ' + words`) and `run_cmd` ran it with `shell=True`, so the
  GUI search query was parsed by `/bin/sh`. The upstream `sanitize_command_input` is a **denylist**
  and does not cover `;` or backticks — verified on the tree: searching
  `firefox; touch /tmp/pwned` **created the file**. Real command execution as the desktop user,
  reachable from the Search field, on a gem that is on by default.
  `run_cmd` now accepts an argument list as well as a string (`Union[str, Sequence[str]]`; a
  sequence sets `shell=False`, and `custom_user` builds `['runuser', '-u', u, '--', *cmd]`), and
  `search()` passes `['pacman', '-Ss', *words.split()]`. Splitting is semantics-preserving —
  verified against real pacman, `-Ss firefox esr` ANDs the two regexes exactly as the shell's
  word-splitting used to. `sanitize_command_input` **stays** as defence in depth (it still strips
  `-flags`, which argv execution would otherwise pass to pacman as options). 9 new tests, incl. a
  canary that fails if an injected command ever runs again. Plan:
  [2026-09-05-search-argv-execution.md](plans/2026-09-05-search-argv-execution.md). Suite now
  **796 Python + 62 JS**. No GUI eyeball needed — search results are unchanged by construction.

- **Long updates now announce and wait for required input (2026-08-29).** Live-log diagnosis found
  that the latest Update All never reached pacman: its root-password prompt received no response
  for five minutes, then the front-end mislabeled `cancelled` as "Bulk upgrade failed." The prior
  run likewise stopped on a timed-out Google Chrome PKGBUILD review. Explicit cancellation is now
  reported separately from failure, and the deadline itself is gone: password, confirmation, and
  blocking-message prompts wait for an explicit answer, post a persistent critical desktop
  notification naming the action, and mark the terminal "Waiting for your input." Answering closes
  the notification and resumes the status. Notifications respect System notifications and carry
  the `atlas-pm` desktop-entry hint; Atlas does not steal focus or move workspaces. Notification
  arguments no longer pass through a shell. Package commands and fail-closed decisions are
  unchanged. Plans: [cancellation clarity](plans/2026-08-29-update-cancellation-clarity.md),
  [attention notifications](plans/2026-08-29-operation-attention-notifications.md). Suite now
  **787 Python + 62 JS**; live Hyprland notification/return flow still needs a manual smoke pass.
- *(2026-08-16 and earlier — the upgrade-pipeline safety work and its holds UI, the 2026-08-01
  doc/repo debt cut, screenshots + release plumbing, public-face cleanup, and the PKGBUILD
  inline reader — all archived in [HISTORY.md](HISTORY.md).)*

---

## Known gaps / gotchas (don't get burned)

Live traps only. Retired ones are in [HISTORY.md](HISTORY.md#retired-gotchas-resolved-or-obsolete--kept-so-they-arent-re-derived).

- **Shell use that is deliberately kept — reviewed 2026-09-05, don't "fix" it.** Three launchers
  run a command line that is *already* a shell command line by specification: `arch`'s and `web`'s
  `launch()` (the package's `.desktop` `Exec=` entry, which may carry quoting/`&&`/redirection) and
  the Debian gem's launch/apt handoff. The **Debian gem's `aptitude.py`** also builds command
  *strings* rather than argv lists; it is off by default, Atlas is Arch-focused (AGENTS.md §3.1),
  and apt cannot be exercised on this box, so restructuring it blind is exactly the risky rewrite
  §3.3 warns about. All of these are in `ALLOWED` in `tests/test_no_shell_execution.py` with their
  reason. **If you convert the Debian gem, do it on a Debian box with a real apt.**
- **`api.py`'s remaining `shlex.quote` calls are correct — leave them.** `get_command` builds a
  command string for the *user* to copy into their own terminal; Atlas never executes it. The three
  `shlex.quote` calls that fed `run_cmd` are gone (argv instead).
- **The dev box still runs stable Atlas 0.16.1.** The 0.16.2 upgrade-safety, holds UI, and update
  cancellation/attention fixes are on `master` but not in `/usr/bin/atlas` until 0.16.2 is released
  (or the `atlas-pm-git` package is installed). Do not mistake a retry in 0.16.1 for verification of
  these fixes. The persistent Hyprland notification + return-to-Atlas flow is not yet live-smoked.
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
- **`atlas-pm-git`'s AUR version string is *supposed* to look stale.** shields.io and the AUR page
  read the `pkgver` frozen in `.SRCINFO`; `pkgver()` recomputes at build time, so installers always
  get HEAD. The `-git` publish workflow only fires on `linux_dist/arch/PKGBUILD` changes, so the
  published label freezes between PKGBUILD edits. **Don't "fix" this with a scheduled `.SRCINFO`
  re-publish** — it fights the Arch VCS convention, spams the AUR with metadata-only commits, and
  adds a standing job holding an SSH key. `paru -Sua --devel` is the supported answer, and the
  README now says so.
- **GitHub Actions `concurrency` + `workflow_dispatch`:** `github.ref` is `refs/heads/<branch>` for
  *every* dispatch, so keying a concurrency group on it puts unrelated dispatches in one group.
  Only one run may sit pending per group, and `cancel-in-progress: false` cancels the **queued**
  run, not the running one — so back-to-back dispatches silently displace each other. Cost us 4 of
  7 backfill runs. Key on the meaningful input instead (`inputs.tag || github.ref`).
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
