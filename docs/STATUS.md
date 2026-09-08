# STATUS — the handoff baton

> **The single most important file for cross-agent continuity** — the live state of the
> project. Read it at the start of every session; update it at the end of every session that
> changes code (AGENTS.md §7).
>
> **Keep this file short.** It is a baton, not a ledger. When an entry stops being live,
> move it to [HISTORY.md](HISTORY.md) (the full shipped record) or delete it. If this file
> passes ~200 lines, it has stopped doing its job — archive again.

**Last updated:** 2026-09-08
**Version:** 0.16.1 (released 2026-07-18, tag `v0.16.1`, release commit `c8b9c37`; CI
auto-published to the AUR). Both AUR packages live: stable **`atlas-pm`** + bleeding-edge
**`atlas-pm-git`**. Next: **0.16.2** — upgrade-pipeline safety, the holds settings UI, and update
cancellation clarity / attention notifications are all implemented but not yet released (plans:
[upgrade-pipeline-safety](plans/2026-08-16-upgrade-pipeline-safety.md),
[gui-upgrade-holds](plans/2026-08-16-gui-upgrade-holds.md),
[cancellation-clarity](plans/2026-08-29-update-cancellation-clarity.md),
[attention-notifications](plans/2026-08-29-operation-attention-notifications.md)).
**Branch:** `master` (= `origin/master`). Always run `git branch` rather than trusting this line.
**Health:** on branch `feat/cross-source-search-normalization` (not yet merged): 811 Python + JS
contract suite green (`fail 0`). `master` itself: 787 Python + 62 JS, CI green on 3.10–3.14.

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

1. **GUI-verify cross-source search normalization** (see Done entry above) — Vatteck's manual pass:
   search `google chrome` and `chrome`, confirm matching grouped results with source pills and an
   "Available from 2 sources" panel.
2. **Relevance inversion (deliberately out of scope in the search-normalization fix).**
   `sortByRelevance` in `main.js` has no source/type term, and its `votes` tiebreaker scores any
   package lacking the field (Arch repo, Flatpak, AppImage) as `-1` — below an AUR package with
   zero votes. At equal name relevance an unvoted AUR package outranks the official signed one.
   `aurVariant()` is also applied to non-AUR names, penalising any package ending in `-git`.
3. **`groupKey` breadth (also deliberately out of scope).** Measured 11/19 on realistic
   Arch-name/display-name pairs. Misses vendor prefixes (`Mozilla Thunderbird`), descriptive
   suffixes (`VLC media player`), Arch packaging suffixes (`libreoffice-fresh`), abbreviations
   (`code` ≙ `Visual Studio Code`). Worth re-measuring now that search no longer hides sources.
4. ~~**GUI eyeball — the one outstanding item.**~~ ✅ **CLEARED 2026-08-01 by Vatteck.** 0.16.1's
   PKGBUILD inline reader in the pre-build review modal (which shipped and released without ever
   being looked at), plus the boot splash and theme-preset/accent contrast, were all walked on the
   real desktop and confirmed good. **Nothing is currently awaiting a GUI eyeball.**
5. **Refresh the screenshots.** All five `docs/screenshots/*.png` predate themes/accents, the
   floating terminal + log highlighting, the dependency tree, the calmed `.pacnew` center, and the
   PKGBUILD reader — `terminal.png` still shows the flat-green sidepane, which no longer exists.
   **Tooling is ready:** `tools/capture-screenshots.sh` (DEVELOPMENT.md §8) floats/sizes the
   window to 1280×800 and crops to it; needs a GUI session, so it's Vatteck's to run.
   *Deliberately not automated with a headless browser* — Chromium isn't WebKitGTK and README
   images from an engine no user runs would be a subtle lie; fixture-driven headless rendering
   belongs in Next #6, where the value is regression testing, not marketing images.
6. **Then pick a real engineering thread** with fresh eyes. Leading candidate: a **render-level test
   harness** for the `main.js` view renderers, since that is exactly where every recent defect lived
   and where the current tests are blind. Alternative: the paused cold-start work below.

### Paused thread — startup memory

Measured and partly fixed (cold peak 528.7 → 451.7 MB via streamed `map_desktop_files`, plus a
cheap read-coalescing guard); the ~200 MB pywebview floor caps the remaining ceiling, and the rest
is a structural arch-gem redesign that needs its own plan. **Do not restart the measurement
work** — full detail, including dead ends already tried, is in
[plans/2026-07-17-memory-baseline.md](plans/2026-07-17-memory-baseline.md).

## Done (recent)

Full record in [HISTORY.md](HISTORY.md). Only the last few entries live here.

- **Cross-source search normalization (2026-09-08) — NOT GUI-VERIFIED.** Bug: searching
  `google chrome` returned only the Flatpak package, while `chrome` returned a correctly grouped
  AUR+Flatpak card with source pills. Multi-source grouping itself was never broken — it was
  starved of input by a search layer matching only one naming dialect at a time. Two root causes
  in `atlas/gems/arch/controller.py`: `_fill_aur_search_results` tested the raw query with `in`
  against an already-normalized AUR index key (`"google chrome" in "googlechrome"` was `False`);
  `__fill_search_installed_and_matched` had a guard `if installed and ' ' not in query:` that
  skipped installed-package matching for any query containing a space. Fixed by extracting the
  matching logic into new `atlas/gems/arch/naming.py` (`normalize_pkg_name`, `match_index_names`,
  `match_installed_names`), delegating both call sites to it, and lowercasing the AUR index build
  in `worker.py` (regenerable cache, so an older index degrades rather than breaks — its private
  `RE_CLEAR_REPLACE` regex is gone). `main.js` gained a standalone `normalizeName()` extracted out
  of `groupKey()`; `tests/fixtures/pkg_name_normalization.json` is asserted from both the Python
  and JS suites so the two normalizers can't drift apart. Design + task plan:
  [2026-09-05-cross-source-search-normalization.md](plans/2026-09-05-cross-source-search-normalization.md),
  [-implementation.md](plans/2026-09-05-cross-source-search-normalization-implementation.md).
  Suite now **811 Python + JS contract suite green (`fail 0`)**.

  **Not GUI-verified — Vatteck's manual pass before calling this done:** search `google chrome` →
  one card with `AUR ● Flatpak ●` pills matching what `chrome` returns; open it → "Available from
  2 sources" panel present; search `chrome` → unchanged from today.

  **Known gap:** the test asserting `not hasattr(worker, 'RE_CLEAR_REPLACE')` guards against the
  duplicate rule returning but asserts an implementation detail — a differently-named duplicate
  regex would pass it.
- **Long updates now announce and wait for required input (2026-08-29).** Live-log diagnosis found
  the latest Update All never reached pacman: its root-password prompt got no response for five
  minutes, then the front-end mislabeled `cancelled` as "Bulk upgrade failed." Explicit cancellation
  is now reported separately from failure, and the deadline itself is gone: password, confirmation,
  and blocking-message prompts wait for an explicit answer, post a persistent critical desktop
  notification naming the action, and mark the terminal "Waiting for your input." Notifications
  respect System notifications, carry the `atlas-pm` desktop-entry hint, and no longer pass
  arguments through a shell; Atlas does not steal focus or move workspaces. Package commands and
  fail-closed decisions unchanged. Plans:
  [cancellation clarity](plans/2026-08-29-update-cancellation-clarity.md),
  [attention notifications](plans/2026-08-29-operation-attention-notifications.md). Suite now
  **787 Python + 62 JS**; live Hyprland notification/return flow still needs a manual smoke pass.
- *(2026-08-16 and earlier — GUI settings surface for upgrade holds, upgrade-pipeline safety,
  doc/repo debt cut, screenshots + release plumbing, public-face cleanup, the PKGBUILD inline
  review modal, the Updates-banner gutters, the dependency-tree rebuild, the terminal dialog + log
  highlighting, the calmed `.pacnew` center — all archived in [HISTORY.md](HISTORY.md).)*

---

## Known gaps / gotchas (don't get burned)

Live traps only. Retired ones are in [HISTORY.md](HISTORY.md#retired-gotchas-resolved-or-obsolete--kept-so-they-arent-re-derived).

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
  and blocks a pywebview worker thread on a `threading.Event`, resolved via `js_api` callbacks.
  Install/cancel/wrong-password behaviour must be confirmed in the running GUI.
- **`request_confirmation` renders input components.** The confirm modal renders
  `MultipleSelectComponent`, `SingleSelectComponent`, `FormComponent`, `TextComponent`; the watcher
  serializes the component tree and applies returned selections back onto the original objects, so
  arch's `request_optional_deps`/`confirm_missing_deps`/`request_providers` read choices as before.
  Covered by `tests/view/webview/test_watcher.py`. Not rendered: option icons, other component types.
- **System tray is AppIndicator/SNI** (`atlas/view/tray.py`) — native on KDE Plasma, **GNOME needs
  the AppIndicator extension** (desktop-side, not our bug). `gi`/AppIndicator are not in the
  project venv, so the GUI and tray run under system Python; tray *logic* is unit-tested, the
  indicator itself is GUI-eyeball-only. Close-to-tray is opt-in (`ui.tray.minimize_to_tray`,
  default off). **KDE custom icons need an absolute file path**, not a theme name —
  `set_icon_theme_path`+`set_icon_full('name')` doesn't resolve on KDE's SNI host (letter-avatar
  fallback); pass an absolute path to `set_icon_full` so the lib sends pixmap data.
- **`refresh_mirrors` is an inert Manjaro leftover — intentionally left.** Uses Manjaro's
  `pacman-mirrors -g`; never runs on Arch/CachyOS (not surfaced in the webview, startup worker
  double-gated off). Superseded by the Arch-correct `regenerate_mirrorlist` (Settings → Mirrors).
  **Decision 2026-06-03: leave it** — removing it means refactoring the startup DB-sync flow for
  zero runtime gain. Not a bug; don't "fix" it.
- **Don't re-attempt a native dependency resolver, and only port CPU-bound ops with small results.**
  `map_missing_deps` is I/O-bound and UI-coupled — a native port needs Rust→Python callbacks and
  isn't faster. Measured: the native pacman info parser hit only ~1.2× (marshalling dominates for
  many dicts) and was reverted; only `map_srcinfo` (~2×, one compact dict) had the right shape.
  Weigh CPU-vs-I/O **and result size** before any native path. (AGENTS.md §3.2 + ROADMAP.)
- **`atlas-pm-git`'s AUR version string is *supposed* to look stale.** shields.io/AUR read the
  `pkgver` frozen in `.SRCINFO`, but `pkgver()` recomputes at build time so installers always get
  HEAD — only the label freezes between PKGBUILD edits. **Don't "fix" with a scheduled `.SRCINFO`
  re-publish** (fights Arch VCS convention, adds a standing SSH-key job). `paru -Sua --devel` is
  the supported answer.
- **GitHub Actions `concurrency` + `workflow_dispatch`:** `github.ref` is the same for every
  dispatch, so keying a concurrency group on it puts unrelated dispatches in one group and
  `cancel-in-progress: false` cancels the queued run, not the running one — back-to-back dispatches
  silently displace each other (cost 4 of 7 backfill runs). Key on the meaningful input instead
  (`inputs.tag || github.ref`).
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

Older entries (2026-06 and the pre-2026-06 Rust/Qt era) are archived in
[HISTORY.md](HISTORY.md#archived-decision-log-2026-06-entries-moved-from-statusmd-on-2026-09-08).

- **2026-09-08** — **Archived older Done entries + two 2026-06 decisions to keep STATUS.md near
  its ~200-line ceiling** (it had drifted to 335 lines). No content lost — see
  [HISTORY.md](HISTORY.md).
- **2026-08-01** — **Split STATUS.md; next phase is verification, not features.** The baton had
  grown to 2,379 lines and become the main cost of re-entering the project. Archived to HISTORY.md.
  Chose "verify and show" (GUI eyeball → screenshots/positioning → render-level test harness) over
  resuming the startup-memory thread, because every recent GUI eyeball found a real defect the test
  suite could not, while the memory work has a ~200 MB pywebview floor capping its payoff.

---

## Template for a STATUS update (copy when editing)

```
**Last updated:** YYYY-MM-DD
- Moved <item> from Next → Done (and older Done entries → HISTORY.md).
- New Current focus: <…>. New Next: <…>.
- New gotcha discovered: <…> (and where it lives).
- Decision: <what + why>.
```
