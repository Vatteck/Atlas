# STATUS — the handoff baton

> **This is the single most important file for cross-agent continuity.** It is the live
> state of the project. Read it at the start of every session; update it at the end of
> every session that changes code (see AGENTS.md §7). Keep it short and current — when an
> item is stale, fix it or delete it.

**Last updated:** 2026-06-17 (latest: a long **GUI-eyeball + diagnostics** stretch. **Fixed a real
correctness bug** — repo updates were under-reported ~60× (3 vs 194) because update detection used the
stale local sync db; now prefers **`checkupdates`** (no-root, fresh) with a `pacman -Qu` fallback
[GUI-verified]. Added a **persistent rotating debug log** at `~/.cache/atlaspm/logs/atlas.log` (+
`sys.excepthook`), which immediately earned its keep: cleaned up per-AUR-package WARNING spam → debug,
made the startup DB-sync skip an INFO with pacman's stderr (was a bare ERROR), and downgraded two
benign once-per-run WARNINGs → INFO. Plus a batch of GUI fixes from real eyeballs: AUR caution banner
above the badges, detail-modal scroll-blank fix, AUR comments moved to Overview + restyled as cards
with shell-code blocks, Flatpak History dates → local time, `credential_harvest` FP on optdepends +
sticky PKGBUILD hover-trail, **cross-source grouping** ("Google Chrome"≙"google-chrome") and **AUR
`-bin`/`-git`/source build variants grouped as one app** with distinct chips + guideline. Suite **700**.
Earlier same day: **`datetime.utcnow()` deprecation cleanup** — all 25 sites →
new naive `commons.util.utc_now()` helper [behaviour-preserving; documents why it stays naive so the
cache-timestamp round-trip isn't broken] + fixed an import-time default-arg bug in `datetime_as_milis`;
suite 690, the utcnow DeprecationWarnings are gone. Earlier same day: **"Why is this installed?"** finished — dependency
attribution names the explicit root(s) that pulled a package in, plus orphan detection tightened to
`pacman -Qdt` semantics [demote when still optional-for an installed package] and the optional-for
packages named; then a **code review** of the whole session's diff — fixed an
`unchecksummed_remote_source` false positive [flag only on explicit SKIP] + documented the
`_function_span` brace limitation. Earlier same day — PKGBUILD audit: external rules-pack loader
[optional local `$CONFIG/arch/audit_rules.json`, additive + fail-closed; signing/remote gated];
`atlas-cli audit-scan` rule-health re-scan [samples live AUR PKGBUILDs, reports per-rule fire rates /
FP drift]; structural rule #3 dropped on measured FP evidence; rule provenance surfaced in the viewer —
rule-id chip + campaign pill + tooltip per finding [GUI-verified]; plus structural/semantic checks:
network-in-package(), unchecksummed-remote-source, and .SRCINFO↔PKGBUILD source-host divergence [wired
through get_pkgbuild] — whole-file, lower-FP than regex; plus the rule-provenance side map and CI
regression corpus — see Done log and plans/2026-06-17-audit-provenance-ui.md +
plans/2026-06-17-audit-structural-checks.md + plans/2026-06-16-audit-rule-maintenance.md.
Prior: History/Activity PR review follow-up: stale detail history reset;
History/Activity completion shipped; planning-doc reconciliation + GUI verification queue captured;
AUR reputation scoring + diff security annotation + batch update risk tiers shipped; reconciled the
stashed mirror regen options — country/protocol/sort in Settings → Mirrors; competitive-research
Themes 1–2 shipped — PKGBUILD audit ruleset 14 → 31, and AUR comments in the detail view; detail pane
reorganized into tabs (Overview/Details/Deps/History) + installed-files & raw-PKGBUILD containment,
PKGBUILD surfaced on the Overview caution banner, comments moved into Details; AUR reputation score
fixed (was computed from an unpopulated pkg object) + made legible with a clickable breakdown and
votes/popularity badges (from GUI eyeballs); competitive-research Theme 4 (AUR request throttle) shipped,
Theme 3 (auth-readiness) dropped as N/A to Atlas's root model — see Done log)
**Version:** 0.12.0 (the polish-and-trust release; 0.11.0 was the first cohesive Atlas release)
**Working branch:** `master` in this checkout (all 2026-06-17 work — audit track, "why installed",
`utcnow()` cleanup, CI 3.14, the GUI-eyeball fixes, debug log, and the `checkupdates` repo-update fix —
landed + pushed to `origin/master`; suite **700**; CI green across Python 3.10–3.14); app work normally
lands on `master` (run `git branch` before acting — branch names in docs go stale)

> Feature wishlist lives in **[BACKLOG.md](BACKLOG.md)** — the longer-horizon menu we pull
> from. This file stays the live baton (in-progress / just-shipped).

---

## Current focus

**A GUI-eyeball + diagnostics pass is complete (2026-06-17); tree green at suite 700 + JS 56.** Working
through the live app on a real desktop surfaced and fixed a string of issues end-to-end (all in the
Done log, all GUI-verified except where noted): the **detail-modal trust/grouping UX** (AUR banner
placement, scroll-blank fix, comments→Overview as styled cards, Flatpak History local time,
`credential_harvest` FP, sticky hover, cross-source + AUR build-variant grouping), a **persistent debug
log** to make future diagnosis possible, and — the headline — a **real correctness bug**: repo updates
were under-reported ~60× because detection read the stale local sync db; now uses `checkupdates`
(no-root, fresh) with a safe `pacman -Qu` fallback (`pacman-contrib` added as optdepends). Decisions
logged: bauh-style startup root prompt is **not needed** (checkupdates gives accurate counts without
auth; lazy-auth model stays); an opt-in "sync on startup" toggle is a low-value future option. No
Rust/Qt revival; no new big architectural migration without a measured reason.

## Next

Everything started this session is complete and documented — nothing half-built. Forward moves come
from **[BACKLOG.md](BACKLOG.md)**, whose agent-actionable *feature* menu is now essentially drained
(remaining items are user-driven: a GUI verification sweep, and a launch-time baseline to measure
*before* any perf work). Highest-value next moves, in order:

0. **Diagnosing GUI issues is now easy** — Atlas writes a persistent rotating log to
   `~/.cache/atlaspm/logs/atlas.log` (every run; `--logs` only adds terminal output). After
   reproducing a bug, read that file for the traceback/warnings. A fresh run is INFO-only, so any
   WARNING/ERROR there is worth a look.
1. **GUI verification sweep** — the **detail-modal surfaces are now largely cleared** this session
   (transaction preview/reputation/votes, PKGBUILD viewer findings+provenance+hover, tabs, comments,
   dependency tabs, source switcher + variant chips, copy command). Still need a real session: **Browse
   landing/AUR buckets, Permissions page icons + override toasts, Activity/History, System Health
   actions, and Settings → Mirrors** (see the queue below).
2. ~~**"Why is this installed?"**~~ ✅ **SHIPPED 2026-06-17** (needs a GUI eyeball) — dependency
   attribution (`installed_because`) names the explicit root package(s). See the Done log +
   [plans/2026-06-17-why-installed.md](plans/2026-06-17-why-installed.md).
3. **Launch-time baseline** — manually measure time-to-window and time-to-first-view before any
   further startup/concurrency changes.

### GUI verification queue

Run these on a real WebKitGTK/pywebview desktop; this environment may not have a display server:

- Browse landing/category polish: category descriptions, breadcrumbs, skeletons, resume chip, and
  AUR discovery buckets with correct Install/Uninstall/Update states.
- Universal transaction preview: install/update/uninstall/downgrade, Update-All aggregate, source
  comparison, AUR reputation score, and batch risk-tier warning text.
- PKGBUILD viewer: detail-page and preview entry points, `.install` tab, copy button, changed-since-
  build diff, inline suspicious-added-line annotations, and per-finding **rule provenance** (rule-id
  chip + "campaign" pill + kind/added/source tooltip).
- Dependency tree: accordion groups and lazy Requires/Build expansion.
- Permissions page: opening directly from the dashboard resolves real icons; Flatpak permission edits
  show a copyable `flatpak override --user ...` toast.
- Activity/History: filter/date grouping, export path/count toast, inline two-click clear, rollback
  affordances, and pacman-log links.
- System Health: keyring and AUR-index cards, Details disclosures, Refresh index, and stale-lock
  removal refusal while pacman is running.
- Settings → Mirrors: active-mirror summary, reflector command preview/copy, regenerate flow, and
  refresh after regenerate.

See BACKLOG's **Non-goals** for what we've decided *against* (AI recs, YaST-style control center,
auto-`.pacnew`-merge, Rust/Qt, fake AUR categories).

> **Handoff note (next agent):** this checkout is on branch `master` (all work pushed to
> `origin/master`); still run `git branch` before committing/pushing rather than trusting this line.
> Release **0.12.0** is tagged and published; `linux_dist/arch/publish-aur.sh`
> was run during the release to sync `atlas-pm-git`. The published `atlas-pm-git` PKGBUILD is
> byte-identical to ours (it's a `-git` pkg, so only PKGBUILD/.SRCINFO *content* changes need a
> re-publish — `pkgver` is computed at build time). Re-run the script whenever the PKGBUILD changes.
> Known external (not Atlas): the AUR `antigravity` 2.0.11 update fails to build — upstream source
> URL 404s (Google pulled the tarball). The maintainer-change advisory can't flag `antigravity`
> (installed before maintainer-caching → no baseline); it works for packages installed since.

Done this session: ✅ CI (GitHub Actions, pytest 3.10–3.13), ✅ dropped Rust, ✅ deleted the
dead Qt-era settings tree, ✅ refreshed stale metadata, ✅ Arch PKGBUILD
(`linux_dist/arch/PKGBUILD`; wheel build verified — pure-Python `py3-none-any`).

The Rust verdict (kept as a lesson): native code only pays off for **CPU-bound ops with a
small result**; Atlas has almost none (it waits on pacman/AUR/network/makepkg). Don't
re-add a native extension without a measured win. Details in the historical
[ROADMAP.md](ROADMAP.md).

---

## Done

- **Fresh repo-update detection via `checkupdates` — fixes silently-missed Arch updates (2026-06-17).**
  Investigating the startup-sync issue surfaced a real correctness bug: `list_repository_updates()` ran
  `pacman -Qu`, which compares against the **local sync db** — only as fresh as the last `pacman -Sy`.
  With the startup root-sync failing (no auth) and no terminal `pacman -Sy`, repo updates released since
  then were **invisible**, while AUR (live RPC) and Flatpak (live remote) showed fine. Measured on the
  dev box: `pacman -Qu` = **3**, real pending = **194**. Fix: prefer **`checkupdates`** (pacman-contrib)
  — it syncs a *temporary* db **without root** (fakeroot) and reports accurately; same `name old -> new`
  format, exit 2 = no-updates. `list_repository_updates()` now tries `_checkupdates_updates()` and
  **falls back to `pacman -Qu`** when checkupdates is absent / errors / times out (offline) → never
  worse than before, accurate when pacman-contrib is present. Extracted pure `parse_repository_updates`.
  `pacman-contrib` added as an **optdepends** in the Arch PKGBUILD. **End-to-end verified live**
  (returns 194). Tests: `RepositoryUpdatesTest` (parse + checkupdates-preferred + exit-2-empty +
  fallback-when-absent + fallback-on-error). Suite **700**. This makes the bauh-style startup root
  prompt unnecessary for update accuracy (lazy-auth model stays); an opt-in "sync on startup" toggle is
  noted as a lower-value future option. **GUI-verified 2026-06-17** (dashboard/Updates shows the real
  repo update count; startup speed fine). Plan:
  [plans/2026-06-17-fresh-repo-updates-checkupdates.md](plans/2026-06-17-fresh-repo-updates-checkupdates.md).
- **Log hygiene from the first real log read (2026-06-17).** The new debug log immediately paid off.
  **(1)** `mapper.check_update` logged **two WARNINGs per installed AUR package** ("no last_modified" +
  "install_date will be used") on every `read_installed` — ~240 of ~305 lines in one session; that's
  the normal AUR fallback path → downgraded to `debug` (kept the rare no-install_date case at WARNING).
  **(2)** The startup `pacman -Syy` failure was logged as **ERROR with no detail**; it's expected
  (startup `prepare()` runs with `root_password=None`, before the user authenticates). Now
  `SyncDatabases` captures pacman's stderr and logs the no-auth skip at **INFO** (Atlas uses the db
  cache, syncs after auth), reserving ERROR for a genuine failure (password supplied) — now with exit
  code + stderr. Open question for the user: whether to optionally prompt for root on startup
  (bauh-style) so the first-screen update counts are fresh — see decision pending. Suite **694**.
- **Persistent rotating debug log (2026-06-17).** Added an on-disk log so issues from a GUI session can
  be diagnosed after the fact (and by an agent) instead of only scrolling past in a terminal. `logs.py`
  `new_logger` now always attaches a **`RotatingFileHandler`** at `~/.cache/atlaspm/logs/atlas.log`
  (`paths.APP_LOG_DIR`/`APP_LOG_FILE`), **1 MiB × 3 backups (~4 MiB cap)** so it's never a standing disk
  cost; terminal output stays gated by `--logs`. The logger is now always live (the file handler needs
  it) — it only silences itself if the file handler can't be created *and* `--logs` is off. `app.py`
  also installs a `sys.excepthook` that routes uncaught exceptions through the logger (so crashes land
  in the file), passing `KeyboardInterrupt` through untouched. Fails open everywhere (a bad log dir
  never breaks boot). Tests: `tests/view/test_logs.py` (file written even with `--logs` off; disabled
  only when no file handler + not enabled). Suite **694**. **For debugging: read
  `~/.cache/atlaspm/logs/atlas.log`** after reproducing an issue.
- **AUR badge: drop the redundant build-kind word now that the chip carries it (2026-06-17).** Follow-up
  eyeball: with the new variant chip, the footer still also printed the build kind as text (`binary · ▲0`,
  `AUR · source · ▲52`) — duplicating the chip. Now the **single-source** AUR tag uses the chip too
  (`AUR · ▲52` for source, `AUR `+bin/git chip otherwise) and the **multi-source** detail shows just
  the votes (`▲N`), no repeated "binary/source" word. The build kind lives in exactly one place (the
  chip). Suite **692** + JS **56**. **Needs a GUI eyeball.**
- **AUR variant pills: distinct chip so "AUR" vs "AUR bin" don't look alike (2026-06-17).** From a GUI
  eyeball on `chrome-remote-desktop` (regular AUR + AUR `-bin`): both pills were the same amber and
  differed only by appended " bin" text, reading as near-duplicates. New `sourcePillHTML` keeps the
  amber **"AUR"** identity but renders the build variant as a distinct **coloured chip** after it —
  `aur-kind-bin` (blue, prebuilt binary) / `aur-kind-vcs` (violet, `-git`/VCS) — so the options are
  tellable at a glance, in both the card switcher and the detail compare panel. Plain-text
  `sourcePillLabel` kept for titles/aria. Tests: `sourcePillHTML` chip cases. Suite **692** + JS **56**.
  **Needs a GUI eyeball.**
- **AUR build-variant grouping (`-bin`/`-git`/source as options of one app) (2026-06-17).** Followed
  up the separator fix to close the suffix gap: `groupKey` now also strips **build-method** suffixes
  (`-bin`/`-git`/`-svn`/`-hg`/`-bzr`/`-cvs`/`-darcs`, chained-safe via `stripBuildSuffix`) so `brave`,
  `brave-bin`, `brave-git` (and a Flatpak "Brave") collapse into **one card with a source switcher**.
  **Channel** suffixes (`-beta`/`-dev`/`-nightly`) are deliberately *not* stripped — those are
  different apps and stay separate (tested). The same-source-dupe guard was upgraded from a raw
  *type* check to an **option signature** (`sourceOptionSig` = type + AUR variant) so two AUR builds
  read as two distinct options instead of being split, while genuine dupes (same type+variant+name)
  still split. To make the options legible: switcher pills + compare-panel rows now label AUR builds
  distinctly (`sourcePillLabel` → "AUR bin"/"AUR git"/"AUR"); `sourceCompareNote` is variant-aware
  (prebuilt-binary / builds-latest-VCS-may-be-unstable / builds-from-source); the compare panel shows
  a **guideline line** explaining `-bin`/`-git`/source when ≥2 AUR variants are present; and
  `compareSourcePreference` gained a tie-break (`aurBuildRank`) so a group **never defaults to a `-git`
  build**. Frontend-only. Tests: extended `testCollapseByNameAcrossSources` (suffix strip, chained,
  bare-"git", bin/git/flatpak→1 card, default-not-git, same-variant dupes split, labels, notes) +
  `testBuildSourceCompareHTML` (variant labels + guideline shown/omitted). Suite **692** + JS **56**.
  **Needs a GUI eyeball** (search "brave"/"chrome" → one card; switch pills; compare panel shows each
  build's version + the guideline). *Known cosmetic:* a grouped card's title is the default option's
  name (e.g. "brave-bin"), not a prettified base — left as-is for honesty (title = active install
  target).
- **Cross-source grouping bridges display-name vs package-name (2026-06-17).** From a GUI eyeball:
  Google Chrome's Flatpak and AUR builds rendered as **two separate cards** because `collapseByName`
  keyed on the exact lowercased name and the Flatpak's display name ("Google Chrome") ≠ the AUR package
  name ("google-chrome"). New pure `groupKey(name)` lowercases **and strips separators** (spaces/`.`/`_`/
  `-`) so the two line up (`googlechrome`), and `collapseByName` keys on it. Separator-only on purpose —
  it bridges punctuation/casing without token-matching that could merge genuinely distinct apps; the
  existing same-name+same-source guard (don't fake a switcher among same-source dupes) and the
  `-beta`/`-bin`-style variant distinction both still hold (verified by tests). Applies everywhere
  `collapseByName` runs (lists, search, suggestions, Browse). Tests: `testCollapseByNameAcrossSources`
  (Flatpak+AUR collapse into one 2-source group; `google-chrome` vs `google-chrome-beta` stay split).
  Suite **692** + JS **56**. **GUI-verified 2026-06-17** (Chrome's Flatpak + AUR now render as one card
  with a source switcher). *Known limitation:* a `-bin`/`-git` suffix still splits
  (`visual-studio-code-bin` ≠ "Visual Studio Code") — out of scope for a conservative separator-only key.
- **PKGBUILD viewer: credential_harvest false positive + sticky hover highlight (2026-06-17).** Two GUI
  bug reports on google-chrome's PKGBUILD. **(1) `credential_harvest` FP:** the rule matched bare daemon
  package names (`gnome-keyring`, `\bkwallet\b`, `login-keyring`), which fire on perfectly normal
  **optdepends descriptions** (`'gnome-keyring: for storing passwords in GNOME keyring'`). Retargeted
  the regex to credential **storage paths/files** — `.local/share/keyrings`, `login.keyring`,
  `/kwalletd/` (plus the kept strong signals `/etc/g?shadow`, `.gnupg`, `.netrc`, `.mozilla`, browser
  config dirs) — so package-name mentions in metadata arrays no longer flag. Regression tests added
  (the two optdepends lines must not fire; a real keyring-file read must). **(2) Sticky hover trail:**
  WebKitGTK can fail to clear CSS `:hover` on fast pointer movement, leaving a trail of highlighted
  code lines. Replaced `.pkgb-line:hover` with a JS-driven single-line highlight (`mouseover` clears the
  previous line + lights the current; container `mouseleave` clears) so exactly one line is ever lit.
  Suite **692**. **Needs a GUI eyeball** (chrome PKGBUILD no longer flags the keyring optdepends; hover
  leaves no trail). *(Note: the `cron_persist` flag on chrome is legitimate-advisory — the Chrome deb
  really does install a cron job; that's the scanner doing its job, not a bug.)*
- **Flatpak History dates → local time (2026-06-17).** From a GUI eyeball: the History tab showed
  `flatpak remote-info --log` commit dates in **UTC** (the log always emits `+0000`), which the old
  parser matched-then-discarded into a naive datetime — so the displayed time was UTC with no label.
  New pure `flatpak.parse_commit_date(raw)` parses the offset (`%z` → aware UTC), converts to the
  system local zone, and returns a **naive local** datetime — local wall-clock so `_json_safe`'s ISO
  string stays clean (`2026-06-09 06:37`, no `+00:00` suffix) but now in the user's own time. Parse
  failure falls back to the raw string (history never breaks over one odd line). `date` is display-only
  (the controller reads only `['commit']`), so no behaviour change beyond the shown time. Tests:
  `ParseCommitDateTest` (tz-independent: naive + re-localizes to the original UTC instant; bad-format
  raises). Suite **692**. **GUI-verified 2026-06-17** (History dates now match the local clock).
- **AUR comments styling — cards + code blocks (2026-06-17).** From a GUI eyeball: the comment thread
  read as an undifferentiated wall of text (author/body run together, separated only by a hairline; and
  pasted shell commands rendered as wrapped prose). Two changes: **(1) card per comment** — each
  `.aur-comment` is now a surface card (bg + border + radius + spacing) with a small **letter-avatar**
  for the author and the date right-aligned, so a long thread visually chunks. **(2) code blocks** —
  new pure `formatCommentBodyHTML(text)` detects runs of **shell-prompt lines** (`$ `/`# `, including
  backslash line-continuations) and renders them as a monospace `<pre class="aur-comment-code">`
  instead of prose; the rest stays linkified prose (`<p class="aur-comment-text">`). Security unchanged
  — bodies are still escaped first, code is escaped (never linkified into live anchors), prose URLs go
  through the existing `linkifyComment`/`safeExternalUrl` path. Tests: extended
  `testBuildAurCommentsHTML` (avatar + initial) + new `formatCommentBodyHTML` cases (prompt→code,
  continuations, prose-around-block, URLs-in-code-not-anchored, plain prose). Suite **690** + JS **55**.
  **GUI-verified 2026-06-17** (google-chrome thread: comments render as avatar cards and the
  `curl | grep | awk` block shows as a monospace code box).
- **AUR comments moved from Details → Overview tab (2026-06-17).** Reverses part of the 2026-06-16
  detail-pane-tabs decision on a GUI eyeball: Overview was too sparse (banner + badges + one-line
  description) while Details carried the table, installed-files, *and* comments. Moved the
  `#detail-comments-section` block to the bottom of the Overview panel (`index.html`); it's filled and
  toggled by `id` and the tab-visibility logic only inspects the deps/history panels, so the relocation
  is safe — no JS logic change (just a stale code-comment touch-up). Comments still start **expanded**
  each open; flagged for review since a heavily-commented AUR pkg will lengthen Overview. Suite **690**.
  **GUI-verified 2026-06-17** (comments now sit at the bottom of Overview; location looks good).
- **Fix: blank detail body after collapsing comments then switching tabs (2026-06-17).** From a GUI
  bug report (google-chrome AUR): collapse the AUR-comments block on the Details tab, switch back to
  Overview → the whole modal body (including the sticky tab bar) went blank. Root cause was **stranded
  scroll**, not the toggle: `.modal-body` is the scroll container and the detail tabs are
  `position: sticky` inside it; switching from a tall, scrolled-down panel to a shorter one left
  `scrollTop` past the new panel's content, so you were looking at empty space with the sticky tab bar
  scrolled out of its (now short) containing block. Fix: reset `detailModal .modal-body` `scrollTop = 0`
  on tab switch and on modal open (so a reopened package also starts at the top). Frontend-only; JS
  contract tests still parse + pass (the scroll behaviour itself is DOM-only, not unit-testable in the
  vm harness). Suite **690**. **Needs a GUI re-eyeball** (collapse comments → Overview is intact; also
  unblocks the pending **Details comments collapse** check). Note: comments living on the **Details**
  tab is *intended* (the 2026-06-16 detail-pane-tabs decision moved comments → Details and put the
  **Review PKGBUILD** button on Overview instead).
- **AUR caution banner above the badge grid (2026-06-17, GUI-verified).** From a GUI eyeball: the
  "From the AUR — community-submitted… review the PKGBUILD" trust banner read better directly under the
  title, *above* the Reputation/Votes/Popularity badges, instead of beneath them. Pure markup reorder —
  swapped `#detail-why-source` and `#rich-badges-grid` in the Overview panel (`index.html`); both are
  filled by `id`, so no JS/CSS change. Suite 690. **GUI-verified.**
- **`datetime.utcnow()` deprecation cleanup (2026-06-17).** Replaced all **25** `datetime.utcnow()`
  call sites (deprecated, slated for removal — noisy under local Python 3.14; CI only runs 3.10–3.13 so
  it was invisible there) with a single new helper `commons.util.utc_now()`. The helper is
  **deliberately naive** (`datetime.now(timezone.utc).replace(tzinfo=None)`) and documents *why*:
  Atlas's cache timestamps round-trip via `utc_now().timestamp()` → `datetime.fromtimestamp(...)`, both
  in naive "UTC wall-clock" space, so an aware value would shift every stored timestamp by the local
  UTC offset and misread existing cache files. **Strictly behaviour-preserving** — not a tz-correctness
  change. Also fixed a latent import-time bug in `datetime_as_milis(date=datetime.utcnow())` (default
  evaluated once at import) → `date=None` sentinel resolving to `utc_now()` at call time. Touched 13
  files (gems arch/debian/web/appimage/flatpak workers+suggestions, `commons/category.py`,
  `view/util/cache.py`). Tests: `UtcNowTest` (naive contract + call-time default) in
  `tests/common/test_util.py`. Suite **690**; the two `datetime.utcnow()` DeprecationWarnings are gone
  (only an external GLib/PyGObject one remains). No GUI surface. Also **added `3.14` to the CI matrix**
  (`.github/workflows/ci.yml`) — Arch now ships Python **3.14** as the system interpreter, so it's what
  Atlas users actually run; CI previously stopped at 3.13, which is why this deprecation was invisible
  there. Pushed to `origin/master`; **CI green across all five legs (3.10–3.14)**.
- **"Why is this installed?" — dependency attribution (2026-06-17).** Finished the BACKLOG item: a
  pulled-in dependency now names the **explicit package(s)** that dragged it in ("Installed as a
  dependency of **gimp**." instead of the generic "…of other packages."). Backend
  `pacman.find_explicit_roots(name)` — a bounded, fail-open, **pure-pacman** reverse walk over
  `map_required_by` (Required By) upward to the explicitly-installed set (`pacman -Qeq`), stopping each
  branch at the first explicit root; capped by `max_visited` (cycle-safe), injectable for tests. Wired
  into `get_dependency_summary` (`installed_because`, only for a non-orphan dependency); frontend
  `buildDependencySummaryHTML` renders the names (cap 4 + "+N more"), falling back to the generic line
  when unresolved. The rest of the item (explicit/dependency/orphan reason + required-by) shipped
  2026-06-05. No new system dep (no `pactree`/`pacman-contrib`). **Orphan accuracy tightened to
  `pacman -Qdt`** (from an eyeball): an orphan candidate is demoted when it's still an *optional*
  dependency of an installed package (new `pacman.map_optional_for`, sharing a refactored
  `_map_qi_set_field` parser with `map_required_by`; fixed a latent multi-line-value bug in the old
  parser). Verified live (`7zip` Optional For parses; `python-build` stays a true orphan). Tests:
  `FindExplicitRootsTest` (8) + `OptionalForTest` (3) + api cases + a JS contract. Suite **687** + JS
  **55**. **Needs a GUI eyeball.** Plan: [plans/2026-06-17-why-installed.md](plans/2026-06-17-why-installed.md).
- **PKGBUILD audit: external rules-pack loader — maintenance step (d), step 1 (2026-06-17).** An
  optional local JSON file (`$CONFIG/arch/audit_rules.json`) can add *regex* rules without an app
  release. **Strictly additive + fail-closed:** a pack never edits/removes a bundled rule, can't shadow
  a bundled id, and any problem (missing file, bad JSON, invalid rule) degrades to *fewer* external
  rules — never a broken scan; a pack also can't disable/suppress a bundled rule. `load_rule_pack(obj)`
  (pure validator → `(rules, meta)`), `register_rule_pack`/`reset_rule_packs`, `load_rule_pack_file`
  (fails closed). Strict per-rule validation: id charset/length + no bundled-collision, `severity ∈
  {warn,info}`, pattern compiles + length-capped, `flags ⊆ {i,m,s}`, `kind ∈ {evergreen,campaign}`.
  `scan()` runs external rules in the same comment-skipping, try/except-guarded loop; `all_rule_ids()`,
  `rule_metadata()`, and `audit-scan`'s universe all include pack rules (so the viewer's rule-id chip +
  kind tooltip surface them for free). `AtlasApi` loads the file once at init (best-effort; no file =
  no change). Only **regex** rules — structural/function checks stay in code. Tests:
  `ExternalRulePackTest` (9). Suite **673**. **Remote signed packs (steps 2–3) are designed but
  deliberately deferred** — see the decision log + plans/2026-06-17-audit-rules-pack-signing.md (a
  permanent supply-chain surface not worth it for an advisory scanner on a `-git`-distributed
  side project). The local loader is the end state unless Atlas moves to slow-release distribution.
  Plan: [plans/2026-06-17-audit-rules-pack.md](plans/2026-06-17-audit-rules-pack.md).
- **PKGBUILD audit: corpus re-scan CLI — maintenance step (c) (2026-06-17).** `atlas-cli audit-scan
  [-n N] [--fp-threshold F] [-f text|json]` samples N random live AUR PKGBUILDs, scans each, and
  reports per-rule fire rates plus two buckets: **FP drift** (rules firing on ≥F of the sample → review
  precision) and **never fired** (kind-aware — a malicious-pattern rule reading 0× on benign packages
  is healthy, so the real signal is an *evergreen* rule that never matches → possible broken regex).
  The rule-health review queue against live data, complementing the fixed regression corpus (step b).
  Pure, offline-testable core in `atlas/gems/arch/audit_rescan.py` (`aggregate_fire_counts`,
  `build_report`, `collect_samples` with injected fetcher+rng, `format_report_text/json`); thin wiring
  in `cli/{cli_args,app,controller}.py` (`CLIManager.audit_rescan` locates the arch manager, pulls
  names via `aur_client.download_names()`, fetches each PKGBUILD via `fetch_aur_file(name, 'PKGBUILD')`).
  PKGBUILD-only (the `.SRCINFO` divergence rule is excluded from the universe); fetches by name-as-base
  so split packages may be skipped (fine for a *sample*). Verified live (6-pkg run flagged
  `weak_checksum`/`skip_checksum`, security rules 0×). Tests: `test_audit_rescan.py` (15). Suite **664**.
  Plan: [plans/2026-06-17-audit-corpus-rescan.md](plans/2026-06-17-audit-corpus-rescan.md).
- **PKGBUILD audit: rule provenance in the viewer UI (2026-06-17).** The kind/added/source we recorded
  in `_RULE_META` is now visible per finding. Backend: `scan()` and `scan_divergence()` attach
  `'meta': rule_metadata(rule_id)` to every finding (no existing keys changed). Frontend: pure
  `findingProvenanceHTML(f)` renders, under each finding, the **rule id** as a mono chip (always —
  makes the heuristic identifiable/reportable) and a **"campaign"** pill *only* for incident-specific
  rules, with the full `Evergreen rule · added … · source: …` in a `title` tooltip; `''` when a finding
  carries no provenance (backward-compatible). Keeps the advisory "read-it-yourself" framing — no
  black-box badge. Tests: JS `findingProvenanceHTML` cases + Python `test_scan_findings_carry_meta`/
  `test_divergence_finding_carries_meta`. Suite **649** + JS **55**. **GUI-verified** on
  `logseq-desktop-git` (rule-id chips + CAMPAIGN pill render correctly). Two follow-up fixes from the
  eyeball, also verified: risk-banner wording now names severities (`N warnings · M notes`, was the
  ambiguous `N lines worth a look · M minor`); and the viewer's code panel no longer clips — the body
  needed `min-height:0` **and** `flex-shrink:0` on its children (the code panel's own `overflow:auto`
  gave it ~0 min-content height, so flex was collapsing it to a sliver). Follow-ups
  still open: filter/hide-by-kind controls; provenance on diff badges. Plan:
  [plans/2026-06-17-audit-provenance-ui.md](plans/2026-06-17-audit-provenance-ui.md).
- **PKGBUILD audit: .SRCINFO↔PKGBUILD divergence — structural step 4 (2026-06-17).** The cross-file
  check (`srcinfo_source_divergence`, WARN): a source **host** declared in the PKGBUILD's `source=()`
  arrays but **absent from `.SRCINFO`** — `.SRCINFO` is what the AUR page and reviewers read while
  makepkg builds the PKGBUILD, so a hidden host means the published metadata conceals where the build
  actually downloads from. `api.get_pkgbuild` now best-effort fetches `.SRCINFO` (`fetch_aur_file(base,
  '.SRCINFO')`) and folds the findings into the PKGBUILD list before the summary; missing/404 `.SRCINFO`
  skips the check (fails open). **Host-set comparison** (not URL diffing) is the key call — `.SRCINFO`
  is the *expanded* PKGBUILD so paths carry `$pkgver`, but hosts are literal; guards strip `name::`/VCS
  prefixes and **skip any `$`-bearing host** (unexpandable → don't false-positive). New
  `scan_divergence(pkgbuild, srcinfo)` (pure, fails open) + `all_rule_ids()` as the single rule-id
  source of truth for the metadata guards. Tests: `SrcinfoDivergenceTest` (7) + api
  `test_srcinfo_divergence_surfaces`/`test_no_srcinfo_skips`. Suite **647**. Only structural step 3
  (source-host ≠ url-host, high-FP) remains — may be dropped. Plan:
  [plans/2026-06-17-audit-structural-checks.md](plans/2026-06-17-audit-structural-checks.md).
- **PKGBUILD audit: structural / semantic checks — step 1 (2026-06-17).** First non-regex detection
  (discovery #4 from the maintenance plan): whole-file checks that read field *relationships*, harder
  to evade and lower-FP than surface patterns. Added a `_STRUCTURAL` pass alongside `_RULES` (analyzer
  `(text) -> [(line_no, line)]`; `scan()` runs regex rules then structural, merges, re-sorts).
  **(1) `network_in_package`** — a network fetch / pipe-to-shell *inside* `package()` (brace-matched
  via `_function_span`); package() should only install built files, so fetching+running code there is
  an install-time backdoor. Network in `build()` is fine (not flagged). **(2)
  `unchecksummed_remote_source`** — an ordered `source=()`↔`*sums=()` parser (`_ordered_arrays`) flags
  a remote **http(s) non-VCS** source whose checksum is SKIP/absent at its index; VCS (`git+…`, pinned
  by commit) and local-file sources are never flagged (those stay the generic `skip_checksum` INFO).
  Both carry `_RULE_META` provenance (evergreen, 2026-06-17) and corpus coverage (benign VCS/verified
  file stays WARN-free; malicious `curl|sh`-in-`package()` + https-SKIP file WARNs). Suite **638** + JS
  **55**. Deferred: source-host≠url-host (high FP — needs to earn its noise) and `.SRCINFO`↔PKGBUILD
  divergence (needs `.SRCINFO` threaded through `get_pkgbuild`). No GUI change. Plan:
  [plans/2026-06-17-audit-structural-checks.md](plans/2026-06-17-audit-structural-checks.md).
- **PKGBUILD audit: rule provenance + regression corpus (2026-06-17).** First implementation of the
  audit-maintenance strategy (answering "how do we find more patterns and keep the ruleset fresh").
  **(a) Rule metadata:** `EVERGREEN`/`CAMPAIGN` constants + a `_RULE_META` *side map* keyed by rule id
  (`kind`/`added`/`source`) and a `rule_metadata(id)` accessor (defaults: evergreen, no source — the
  pre-metadata baseline for the original hand-written rules). Kept as a side map so the
  security-sensitive regex tuples stay untouched. Recorded only what we know: the 2 Atomic Arch
  campaign rules (`npm_install_unknown`, `temp_upload_service`) and the 17 ks-aur-scanner-derived
  evergreen rules (2026-06-16); the campaign split makes dead-campaign rules *retirable* so they don't
  rot into low-signal noise. **(b) Regression corpus:** `tests/gems/arch/audit_corpus/{benign,malicious}/
  *.pkgbuild` + `test_pkgbuild_audit_corpus.py` loader — benign realistic PKGBUILDs **must not raise a
  WARN** (INFO allowed), malicious whole-file samples (reverse shell, credential exfil, persistence/
  obfuscation) **must raise ≥1 WARN**. Grow by dropping a file in. Guard tests on the metadata map
  (every key real, every campaign rule has a source, counts add up). Suite **630** + JS **55**. No GUI
  surface yet (follow-up: show kind/source in the PKGBUILD viewer). Plan:
  [plans/2026-06-16-audit-rule-maintenance.md](plans/2026-06-16-audit-rule-maintenance.md).
- **Cross-view install queue — competitive-research Theme 5 v1 (2026-06-16).** A persistent basket for
  collecting packages to install together while browsing, instead of the per-view Select mode that
  reset on navigation. Persistent `installQueue` of pkg snapshots in `localStorage`
  (`atlas_install_queue`), loaded on boot (pure `pkgSnapshot`/`queueUpsert` + stateful
  `queueAdd/Remove/Has/Clear`/`updateQueueBadge`). Entry points: a "＋ Queue / ✓ Queued" toggle on every
  not-installed card (allowed even mid-install) and in the detail-modal footer. A topbar **Queue (N)**
  button (hidden when empty) opens a review modal with per-row **Remove**, **Clear**, and **Install
  all** — which routes the queued ids through the existing `batch_install` and clears on success.
  Install-only basket. Tests: `main_js_contracts::testInstallQueueHelpers`. Suite **622** + JS **55**.
  **Needs a GUI eyeball.** Deferred follow-ups: aggregate queue preview, auto-remove on individual
  install, uninstall basket. **Theme 5 completes the competitive-research themes (1,2,4,5,6 done; 3
  N/A).** Plan: [plans/2026-06-16-theme5-package-queue.md](plans/2026-06-16-theme5-package-queue.md).
- **Fuzzy search local filter + fallback — competitive-research Theme 6 part 2 (2026-06-16).** Searching
  from the **Installed**/**Updates** views now **filters that view's own list** (pure
  `filterLocalPackages`: exact name/description substring first, relevance-ordered; else, for queries
  ≥3 chars, a thresholded fuzzy *name* fallback via `fuzzyScore ≥ 8` so `frfx` still finds `firefox`)
  instead of running a global cross-source `search`. Uses the already-cached full list (`localListFor`)
  — no extra backend call. **Intended behaviour change:** to find/install a *new* package, use
  Browse/Dashboard search; the two finite views now self-filter. Client-only. Test:
  `main_js_contracts::testFilterLocalPackages`. JS **54**. **Needs a GUI eyeball + user sign-off on the
  behaviour change.** Theme 6 is now complete (parts 1 + 2). Plan:
  [plans/2026-06-16-theme6-fuzzy-search.md](plans/2026-06-16-theme6-fuzzy-search.md).
- **Fuzzy search re-rank — competitive-research Theme 6 part 1 (2026-06-16).** Search results from the
  backend (`pyApiCall('search', …)`, which matches name/description/keywords) are now **re-ranked
  client-side** so the closest *name* match is first — `widg` puts `widget` on top instead of buried.
  Pure `rerankByFuzzy(results, query)` reuses the command-palette `fuzzyScore`, is stable on ties, and
  **never drops a result** (non-matching items keep backend order below the matches); applied before
  `writeToCache` so cached queries keep the order. Empty query / <2 results / bad input pass through.
  Client-only, no backend change. Test: `main_js_contracts::testRerankByFuzzy`. JS **53**. **Needs a
  GUI eyeball** (partial/typo'd query surfaces the obvious package first). Part 2 (thresholded fuzzy
  *fallback* for the finite Installed/Updates lists) is still planned, not built. Plan:
  [plans/2026-06-16-theme6-fuzzy-search.md](plans/2026-06-16-theme6-fuzzy-search.md).
- **AUR request throttle — competitive-research Theme 4 (2026-06-16).** `AURClient` now enforces a
  150ms minimum gap between consecutive AUR requests (`_throttle()` via `time.monotonic`/`time.sleep`,
  `_MIN_REQUEST_INTERVAL`), called by every network method (`search`, `get_info`, `get_src_info`
  cache-miss, `download_names`). aurweb asks clients not to burst the RPC; the bulk `get_info` is
  already batched, so this mainly smooths the sequential per-package `.SRCINFO` fetches during
  dependency resolution. Scoped to the AUR client so non-AUR `HttpClient` traffic is untouched. Flat
  delay, no token bucket (the RPC isn't high-throughput). Tests: `test_aur.py::ThrottleTest`. Suite
  **622**. **Theme 3 (auth-readiness check) was dropped as not-applicable:** Atlas doesn't rely on
  sudo's credential cache — it holds the password in `_root_password` and re-supplies it via `sudo -S`
  on every privileged call (`validate_root_password` runs `sudo -k`), so a long build can't fail from
  a sudo timeout. Plan:
  [plans/2026-06-16-competitive-research-improvements.md](plans/2026-06-16-competitive-research-improvements.md)
  (Themes 1, 2, 4 done; 3 N/A; 5–6 exploratory).
- **AUR reputation: correct score + legible breakdown + filled badge grid (2026-06-16).** A GUI
  eyeball showed android-studio (a hugely popular AUR pkg) as **15 · Risk** with no explanation. Root
  cause was a real bug: `calculate_aur_risk_score` read votes/popularity/age off the **pkg object**,
  which is unpopulated in the detail/preview flow — so those factors scored 0 even though
  `get_aur_meta`/`_preview_aur` had *just* fetched the RPC `info` with the real numbers (15 was purely
  `maintainer_stable`). Fix: the scorer takes an `info=` param and prefers the fresh RPC values
  (`NumVotes`/`Popularity`/`FirstSubmitted`/`Maintainer`); all three callers (incl. the batched
  `get_update_risk_tiers`) pass it. Legibility: the scorer now returns a `breakdown` (per-signal
  value + points/max), the **Reputation badge is clickable** → a popup (`reputationPopupHtml`)
  showing how each signal contributed + the "not a safety check" disclaimer, and the empty Overview
  badge grid is filled with the score's own inputs — **Votes / Popularity** badges (+ **Out of Date**
  when flagged). Tests: `test_aur_risk.py` (info-overrides-pkg regression + breakdown),
  `test_api.py::AurMetaTest`, `main_js_contracts::testReputationPopupHtml`. Suite **618** + JS **52**.
  **GUI-verified 2026-06-17** (android-studio detail modal: scores a realistic **100 · Trusted** — was
  15 · Risk before the fix — with the **Votes 1,134 / Popularity 9.13** badges filling the grid; and
  clicking the **Reputation badge opens the breakdown popup**). Plan:
  [plans/2026-06-16-aur-reputation-legibility.md](plans/2026-06-16-aur-reputation-legibility.md).
- **Detail pane tabs + wall-of-text containment + PKGBUILD/comments placement (2026-06-16).** From two
  GUI eyeballs: the detail modal's installed-files list (arch `pacman -Qlq`, often thousands of
  entries) **and** the raw `pkg build` PKGBUILD text both ballooned into giant table cells, and the
  body had grown enough sections to warrant tabs. Reworked `.modal-body` into a `#detail-tabs` tablist
  + `.detail-panel`s — **Overview / Details / Dependencies / History** — keeping every existing section
  ID so the async renders are unchanged. Empty tabs auto-hide via pure `computeDetailTabs(content,
  active)` (active-tab fallback), applied by `updateDetailTabs` on open + after each section settles.
  Installed files now render as a collapsible **filterable, scrollable, counted** block (pure
  `buildInstalledFilesHTML`, capped at 2000 rows) instead of a table cell; the raw PKGBUILD row is
  dropped from the table (`SKIP_DETAIL_KEYS`). Per feedback, the **PKGBUILD is surfaced on Overview** —
  a "Review PKGBUILD →" button inside the AUR caution banner (`renderWhySource`, opens the full
  viewer) — and **AUR comments moved into the lower half of the Details tab** as a collapsible
  (hide/show) block; the now-empty **Build & Trust tab was removed**. Also fixed a latent
  `--accent-primary` → `--accent-color` CSS var typo. Pure frontend (no backend change). Tests:
  `main_js_contracts::testBuildInstalledFilesHTML` + `testComputeDetailTabs`. Suite **614** + JS **51**.
  **GUI-verified 2026-06-17:** tab bar renders, **tab switching works**, the Overview "Review PKGBUILD"
  button shows, and the **installed-files filter/containment** works on a thousands-of-files package.
  **Comments collapse/expand confirmed working** (now on the Overview tab — see the move entry above).
  **Empty-tab auto-hide verified-as-designed 2026-06-17:** on a Flatpak (geforcenow) the Dependencies
  and History tabs correctly *stay* because both panels have real content (Deps shows the "bundled in a
  runtime" explainer; History shows the ostree commit log) — `computeDetailTabs` only hides a genuinely
  empty deps/history panel, which is covered by its unit test. So nothing to fix; the queue item is
  closed. Plan:
  [plans/2026-06-16-detail-pane-tabs.md](plans/2026-06-16-detail-pane-tabs.md).
- **AUR comments in the detail view — competitive-research Theme 2 (2026-06-16).** AUR package
  comments (build-fix tips, security warnings, orphan/broken context) now show in a lazy "AUR comments"
  section of the detail modal. The AUR RPC has no comments endpoint, so the package page is scraped:
  new pure parser `atlas/gems/arch/aur_comments.py` (`parse_comments` → `[{author, date, body}]`,
  network-free, unit-tested), and `AtlasApi.get_aur_comments(pkg_id)` resolves the pkgbase, fetches once
  per session via the shared `HttpClient`, caches per base, and fails open. **Security choice:** bodies
  are reduced to **plain text** in the parser (we never re-inject scraped third-party HTML into
  WebKitGTK); the frontend (`buildAurCommentsHTML`/`linkifyComment`) escapes the text and linkifies bare
  http(s) URLs through `safeExternalUrl`. AUR-only; non-AUR/no-comments keep the section hidden. Tests:
  `test_aur_comments.py`, `test_api.py::AurCommentsTest`, `main_js_contracts::testBuildAurCommentsHTML`.
  Suite **614** + JS **49**. **Needs a GUI eyeball** (open an AUR package with comments → section
  renders, links open externally). Plan:
  [plans/2026-06-16-competitive-research-improvements.md](plans/2026-06-16-competitive-research-improvements.md)
  (Theme 2).
- **PKGBUILD audit ruleset expansion — competitive-research Theme 1 (2026-06-16).** Grew the advisory
  PKGBUILD/.install scanner from **14 → 31 rules** (`pkgbuild_audit.py`), distilled from ks-aur-scanner's
  detection categories — all pure pattern matchers, no external tools/network/ML, fail-open, advisory-only
  (no "safe" verdict). New rules: reverse shells (`reverse_shell_bash`/`_lang`/`_listener`), credential
  theft (`credential_harvest`, `ssh_key_exfil`), persistence (`systemd_timer_create`, `cron_persist`,
  `rc_local`, `shell_function_inject`), obfuscation (`printf_assembly`, `gzip_payload`, `xxd_decode`),
  `dep_confusion` (provides=/conflicts= a core package), weak integrity (`weak_checksum`, `http_source`),
  privesc (`suid_capability`, `ld_preload`). New helper `_has_insecure_http_source` (skips git+http /
  localhost). Each rule has a positive + false-positive-safe test in
  `test_pkgbuild_audit.py::CompetitiveResearchRuleTest`; `CLEAN_PKGBUILD` stays at zero findings.
  Suite **603** + JS **48** green. **Needs a GUI eyeball** (open a PKGBUILD containing one of the new
  patterns → the flagged line shows in the viewer with its rule/why). Plan:
  [plans/2026-06-16-competitive-research-improvements.md](plans/2026-06-16-competitive-research-improvements.md)
  (Theme 1; Themes 2–6 remain).
- **History/Activity completion (2026-06-16).** Finished the remaining History/Activity backlog
  items: `activity_log.py` now automatically compacts the local JSONL feed to the newest 1000 valid
  entries (checked every 25 writes), and installed package detail modals show a compact per-package
  Atlas activity panel with recent actions, failures, timestamps, plus a jump to the full Activity
  page filtered by that package. PR review follow-up: opening a non-installed package now clears any
  stale package-history section left by the previous modal, and the mock frontend API includes the
  package-activity endpoint for dev/test fallback. This reuses the existing local activity feed and
  fails open so the detail modal never blocks. Plan: [plans/2026-06-16-history-polish.md](plans/2026-06-16-history-polish.md).

- **AUR reputation scoring + diff security annotation + batch update risk tiers (2026-06-16).**
  Three security-trust features on top of the existing PKGBUILD-audit/maintainer-change
  infrastructure (no new network calls — pure computation on AUR RPC data Atlas already fetches).
  **(1) Composite AUR reputation score** — new `atlas/gems/arch/aur_risk.py`
  (`calculate_aur_risk_score(pkg, maintainer_changed) -> {score 0-100, tier, factors}`, weighted
  votes/age/orphan/maintainer-stability/popularity); surfaced via `get_aur_meta()` and
  `_preview_aur()` in `api.py`, a "Reputation" badge on the AUR detail page, and a score indicator
  in the install/update preview modal. **(2) Diff security annotation** — `pkgbuild_audit.diff_lines()`
  gained `annotate=True` (attaches `scan()` findings to each added diff line); `get_pkgbuild()`'s
  "changed since your build" diff now passes it through, and the PKGBUILD viewer's diff tab shows
  an inline `⚠ rule_id` badge on suspicious added lines. **(3) Batch update risk tiers** — new
  `get_update_risk_tiers(pkg_ids)` makes **one** batched AUR RPC (`aur_client.get_info`) to score
  every pending AUR update at once (avoids an N+1 RPC regression in the otherwise-zero-server-calls
  Update-All preview); `updateAllBtn` calls it alongside the existing news/.pacnew checks and
  `buildUpdateAllPreviewData` adds a safe/caution/risk breakdown note + names any high-risk packages
  in the warnings list. Fails open throughout (RPC error → 'caution', never silently 'safe'); never
  gates — Update All still updates everything in one shot. 573 tests + 45 JS green. New tests:
  `tests/gems/arch/test_aur_risk.py` (6), `pkgbuild_audit` diff-annotation cases,
  `testBuildUpdateAllPreviewData` tier cases. Plan:
  [plans/2026-06-16-aur-reputation-and-risk-tiers.md](plans/2026-06-16-aur-reputation-and-risk-tiers.md).
- **Mirror regenerate options — country / protocol / sort (2026-06-07).** Settings → Mirrors no longer
  regenerates `/etc/pacman.d/mirrorlist` with a fixed reflector command — the user can now pick a
  **country**, one or more **protocols** (https/http/rsync), and a **sort** order, with the previewed
  command updating live (nothing hidden). **Reflector-only** (rate-mirrors doesn't take the same flags
  → keeps its fixed command and shows no controls). Backend: a curated static `_MIRROR_COUNTRIES` list
  (~43 ISO codes, no network), `_sanitize_mirror_options` (whitelists country/protocols/sort, clamps
  `latest` to [5,50] — these flow into a *root* argv so nothing outside the known sets is accepted),
  `_mirror_regen_cmd(options)`, a cheap `preview_mirror_command(options)` (no file read, for the live
  preview), and `get_mirror_status(options)` / `regenerate_mirrorlist(options)` threading options
  through; `get_mirror_status` exposes `countries`/`protocols`/`sorts`/`options` only when reflector is
  the tool. Frontend: pure `buildMirrorOptionsHTML(mirror)` (country/sort selects + protocol
  checkboxes; `''` for rate-mirrors), `readMirrorOptionsFromDOM`, options persisted to localStorage
  (`atlas_mirror_opts`) + seeded into the initial status call; change handlers recompute the previewed
  `<code>` via `preview_mirror_command`, and regen/copy use the live selection. Tests:
  `test_api.py::ArchSafetyNetTest` mirror-options block (+11: sanitize defaults/whitelist/clamp/keep,
  argv reflects options, status exposes/omits per tool, preview builds + fails open, regen passes
  flags) + `main_js_contracts::testBuildMirrorOptionsHTML`. Suite **570** + JS **46**;
  `git diff --check` clean. **Needs a GUI eyeball** (Settings → Mirrors: pick a country/sort/protocol →
  command preview updates live; Regenerate uses it; rate-mirrors-only systems show the plain button).
  Plan: [plans/2026-06-07-mirror-regen-options.md](plans/2026-06-07-mirror-regen-options.md).
- **GUI eyeballs confirmed (2026-06-07).** The two pending verifications from the 0.12.0 deferred-tail
  both look good: Permissions-page icons (open straight from the dashboard → real icons, not letter
  avatars) and the deferred-tail (Flatpak override copy command + Activity Export/Clear). Marked
  GUI-verified in their Done entries.
- **Release 0.12.0 — the polish-and-trust release (2026-06-06).** Bumped `__version__`
  0.11.0 → **0.12.0** (`atlas/__init__.py`, README status line, PKGBUILD `pkgver`), wrote a themed
  `CHANGELOG.md` 0.12.0 section (everything since the `v0.11.0` tag — Attention Center, command
  palette, Browse 2.0 + AUR buckets, detail-page/PKGBUILD/dependency work, universal transaction
  preview + terminal polish, history center, copy-exact-command, System Health + `.pacnew` cockpit,
  GUI polish, the sidebar/Browse/icon fixes, and the security pass). Tagged **`v0.12.0`** and pushed;
  ran `linux_dist/arch/publish-aur.sh` to sync `atlas-pm-git`. 559 tests + 45 JS green. Plan basis:
  [plans/2026-06-04-release-0.11.0.md](plans/2026-06-04-release-0.11.0.md) (same process).
- **Browse landing polish — sidebar icons, category/AUR grid (2026-06-06).** Pre-release visual sweep
  from a GUI eyeball: (1) **distinct sidebar icons** — Dashboard/Browse shared a grid glyph and
  Health/Activity shared an ECG glyph; Browse → compass, Activity → list, so all ten nav icons differ.
  (2) **Unified Browse rows** — the category cards sized each tile to its text (ragged columns, an
  8→6+2 wrap gap) and the AUR chips were a different size; both rows now lay out on one fixed 4-column
  grid with the same rich tile (categories = 2 even rows, AUR = 1, columns aligned, no gap). CSS/markup
  only; JS 45.
- **Fix: Permissions-page icons stuck on letter avatars (2026-06-06).** The Permissions master list
  rendered every app as a letter avatar. Root cause: `renderPermsAppList` observed its lazy icons only
  `if (window.iconObserver)`, but that shared IntersectionObserver is created inside `deferredIconLoad()`,
  which only runs when a **package grid** renders. Since the app lands on the **dashboard** (Attention
  Center, no grid — a 2026-06-04 change), opening Permissions first left the observer undefined → the
  guard silently skipped → icons never resolved (their remote Flathub-CDN `data-src` was never probed).
  Fix: extracted observer creation into `ensureIconObserver()` (idempotent, on `window`), called by both
  `deferredIconLoad` and the perms list; the perms list now also sets `data-pkgicon` as a backend
  fallback for apps with no embedded/remote icon. Test:
  `main_js_contracts::testPermsListEnsuresIconObserver`. JS **45**. **GUI-verified 2026-06-07** (open
  Permissions straight from the dashboard → real icons, not letters).
- **Deferred-tail: flatpak-override copy + History log clear/export (2026-06-06).** Cleared the two
  explicitly-deferred small items. **(1) `flatpak override` copy completes "Copy exact command"** —
  every Flatpak permission *edit* now surfaces the exact `flatpak override --user <flag> <app_id>` it
  ran (copyable — click the toast; "nothing hidden from CLI users"). New pure
  `permissions.override_command(app_id, flag)` (shlex-quoted); the four `AtlasApi.set_flatpak_*`
  methods (toggle/filesystem/bus/env) return `{'status':'ok','command':…}` computed from the same pure
  `*_flag` helpers the gem applies (so it's exactly what ran); failure → error, no command. Frontend:
  `showToast` gained an optional `copyText` (click-to-copy + hint); shared `permissionUpdatedToast(r)`
  shows `Updated · <command>` (copyable) or the old generic toast, wired into all four edit paths +
  the detail-modal quick-editor popup. **(2) History log clear/export** — the Activity page filter bar
  gained **Export** (`export_activity` → `~/atlas-activity.json`, toasts count+path) and **Clear**
  (`clear_activity` → removes the local JSONL via `clear_activity_log()`, thread-safe/idempotent; the
  button **confirms inline** — one re-click within 3s, `btn-danger` — no WebKitGTK `confirm`; clears
  Atlas's feed only, never `/var/log/pacman.log`). Tests: `test_permissions.py::test_override_command`,
  `test_api.py::FlatpakOverrideCommandTest` (5) + `ActivityLogTest` (4), `test_activity_log.py` (4),
  `main_js_contracts::testPermissionUpdatedToastSurfacesCopyableCommand`. Suite **559** + JS **44**;
  `git diff --check` clean. **GUI-verified 2026-06-07** (toggle a Flatpak permission → copyable override
  command; Activity → Export writes the file; Clear → re-click confirms → list empties). Plans:
  [plans/2026-06-05-copy-exact-command.md](plans/2026-06-05-copy-exact-command.md) (inc. 3),
  [plans/2026-06-05-history-rollback-center.md](plans/2026-06-05-history-rollback-center.md) (inc. 3).
- **Security + webview loading pass (2026-06-06).** Focused hardening/optimization pass for the
  pywebview surface. **Security:** `atlas.commons.html.bold()` and `link()` now HTML-escape text,
  href attributes, and visible URL text before those helper strings flow into webview-rendered
  modal/status HTML. `AtlasApi.open_url()` now parses URLs with `urlsplit`, rejects control/space
  characters and missing hosts, and only opens parsed `http`/`https` schemes (case-insensitive).
  The JS side now routes external-open affordances through `safeExternalUrl()`/`openExternalUrl()`;
  Arch news links and PKGBUILD metadata/source links only render clickable anchors for safe parsed
  HTTP(S) URLs. Added `tests/common/test_html.py` for the injection cases, kept `strip_html`
  behavior pinned, and extended `OpenUrlTest` + `main_js_contracts` for URL-sink regressions.
  **Loading:** dashboard `renderAttentionCenter()`, the sidebar `refreshUpdatesBadge()`, and the
  no-query Updates view now share one cached/in-flight `get_updates('all')` request via
  `getUpdatesCached()`, removing duplicate expensive Updates reads across startup and rapid
  Updates-view navigation. `setUpdatesBadge()` now writes an explicit string to match browser
  `textContent` coercion. Tests: `tests/common/test_html.py`, `tests/view/webview/test_main_js.py`,
  `tests/view/webview/test_api.py::OpenUrlTest`; subtree `tests/view/webview` = **194 passed**;
  full suite = **545 passed, 3 warnings**; added-line static scan clean; `git diff --check` clean.
  Plan: [plans/2026-06-06-security-webview-loading.md](plans/2026-06-06-security-webview-loading.md).
- **System Health follow-ups (2026-06-05).** Extended the System Health page (the BACKLOG "possible
  follow-ups" on the shipped Health page). **Two new checks** (cheap, concurrent, fail-open in
  `get_system_health`): **keyring freshness** (`_keyring` — mtime of the `archlinux-keyring` local-db
  entry → `age_days`; >90d warns, since a stale keyring is the classic "invalid/corrupted package (PGP
  signature)" cause; the `more` disclosure shows the refresh command) and **AUR index age**
  (`_aur_index` — mtime of `AUR_INDEX_FILE`; >14d → info + a Refresh action; card omitted when no index
  exists). **Gated "Remove stale lock" action** — the pacman-lock card now offers `remove-lock` →
  `AtlasApi.remove_pacman_lock()`, which **refuses while a pacman process is actually running**
  (`pgrep -x pacman`) and otherwise removes `/var/lib/pacman/db.lck` via the root broker. New
  `refresh_aur_index()` reuses the arch gem's `_update_aur_index` (non-privileged). **Per-check details
  disclosure** — an optional `more` field renders an expandable "Details" block (commands / why it
  matters). Tests: `SystemHealthTest` (+4: remove-lock no-lock / refuses-when-running / removes-when-idle,
  refresh-aur-index) + `testSystemHealthChecks` (keyring tones + command, aur-index action, lock action +
  more). Suite **540** + JS 39. **Needs a GUI eyeball** (keyring/AUR-index cards; expand Details; with a
  stale `db.lck` present → Remove stale lock; Refresh index). Plan:
  [plans/2026-06-04-system-health.md](plans/2026-06-04-system-health.md).
- **Browse 2.0 polish (2026-06-05).** Frontend-heavy polish of the Browse landing + category pages
  (the BACKLOG "Browse 2.0" item). (1) **Richer category cards** — pure `buildCategoryCardHTML` adds
  an **icon + short description** (descriptions added as a 6th element of `CATEGORY_BUCKETS`, surfaced
  by `get_categories`); **no count** (deliberate — the repo-only count understates a bucket that also
  lists Flathub apps; AUR buckets keep their truthful count). (2) **Breadcrumbs** — `browseCategoryHeader`
  now renders `Browse / <Category>` (the Browse crumb returns to the landing), replacing the bare
  "← Categories" button. (3) **Persist last-opened category** — `setLastBrowseCategory`/
  `getLastBrowseCategory` (localStorage `atlas_last_browse_cat`); the landing shows a pure
  `buildResumeBrowseHTML` "↩ Resume <label>" chip that reopens it (convenience, not auto-nav). (4)
  **Better category-page skeletons** — `renderCategoryPackages` shows the breadcrumb + `getSkeletonGridHTML()`
  while loading instead of a bare spinner. Tests: `BrowseCategoryTest` (description assertion) +
  `main_js_contracts::testBrowseLandingBuilders` (card icon/label/description/no-count, resume chip).
  Suite **536** + JS **39**. **Needs a GUI eyeball** (landing cards w/ descriptions; open a category →
  breadcrumb + skeleton; return → resume chip reopens it). Plan:
  [plans/2026-06-05-browse-2.0-polish.md](plans/2026-06-05-browse-2.0-polish.md).
- **Copy exact command — increment 1 (2026-06-05).** The pre-flight transaction preview now has a
  **"⧉ Copy command"** button that copies the equivalent terminal command for that exact transaction
  (Atlas's "honest enough for Arch people" angle — nothing hidden from CLI users; the BACKLOG "Copy
  exact command" item). Backend `AtlasApi.get_command(pkg_id, action)` → `{command, note}` from the
  real package object: repo → `sudo pacman -S/-Rns <name>`; AUR → `git clone …<package_base>.git && cd
  … && makepkg -si` (+ a `paru -S` helper note) / `pacman -Rns` for uninstall; Flatpak →
  `flatpak install flathub/update/uninstall <app_id>` (uses `pkg.id`, the real app id). `''` for
  actions with no clean one-liner (downgrade) → the button hides; `shlex.quote`d; never raises.
  Frontend: footer button in a new `.modal-footer-left` group beside "View PKGBUILD" (single-package
  install/update/uninstall only — not Update-All); `copyEquivalentCommand` copies + flashes "✓ Copied"
  + toasts the command/note. Tests: `test_api.py::CommandTest` (6). Suite **536** + JS 38. **Needs a
  GUI eyeball** (repo/AUR/Flatpak install preview → Copy command → correct command on the clipboard +
  toast). **Deferred:** copy on the detail page; `flatpak override` copy on the Permissions page;
  `reflector` copy in Mirrors (already previews the command). Plan:
  [plans/2026-06-05-copy-exact-command.md](plans/2026-06-05-copy-exact-command.md).
  **Increment 2 (2026-06-05):** added the two other surfaces — (a) a left-aligned **"Copy command"**
  button in the **detail-modal footer** (arch/aur/flatpak), copying the command for the *primary
  action* (install/update/uninstall) via the same `copyEquivalentCommand`; (b) a **"Copy command"**
  button in **Settings → Mirrors** beside Regenerate that copies the already-previewed reflector
  command (`get_mirror_status().command`). No backend change (reuses `get_command`/`get_mirror_status`).
  Suite **536** + JS 38. The **detail-modal footer "Copy command" is GUI-verified 2026-06-17**
  (android-studio → copies the command to the clipboard); the **Settings → Mirrors** copy button still
  wants an eyeball. Only **`flatpak override` copy on the Permissions page** remains deferred (per-edit
  command shape; lower value).
- **Dependency tree view (2026-06-05).** Completed the detail-page Dependencies section into a full
  relationship picture + a drill-down tree (the BACKLOG "Dependency tree view" item). **Backend:**
  `get_dependency_summary` now additionally returns `makedepends`/`checkdepends` (AUR only — binary
  repos don't carry build deps in `pacman -Si`), `conflicts`/`provides` (repo: `map_updates_data`
  `c`/`p`; AUR: `get_info`), and `replaces` (repo: `map_conflicts_with` `r`; AUR `get_info`) — all
  additive + **fail-open per field**. New cheap `get_subdeps(name)` returns a single package's direct
  requires (repo via `map_updates_data`; fail-open → leaf) for lazy expansion. **Frontend:**
  `buildDependencySummaryHTML` renders new accordion groups (Build / Provides / Conflicts / Replaces)
  alongside Requires / Optional / Required-by + the install-reason banner; **Requires + Build are
  drill-down trees** — each dep is an expandable node (pure `buildDepNodesHTML`, `data-dep` = bare
  name with version constraint stripped) that lazily fetches `get_subdeps` on first expand and renders
  its requires as the same nodes (drill arbitrarily deep, one cheap pacman call per level, bounded by
  clicks). Optional/Provides/Conflicts/Replaces/Required-by stay flat chips (relationships, not trees).
  Wired by `wireDependencyTree` (delegated click, load-once). Tests: `DependencySummaryTest` (new
  groups repo+AUR, fail-open) + `get_subdeps` (2) + `main_js_contracts` (new groups, nodes,
  constraint-stripping). Suite **530** + JS 38. **Needs a GUI eyeball** (repo pkg: Provides/Conflicts;
  AUR pkg: Build deps; expand a Requires node → sub-deps load). Plan:
  [plans/2026-06-05-dependency-tree-view.md](plans/2026-06-05-dependency-tree-view.md).
- **PKGBUILD viewer — first-class AUR build-recipe reader, increment 1 (2026-06-05).** The BACKLOG
  "PKGBUILD viewer as a first-class UI" item — Atlas's potential signature AUR feature. The advisory
  scanner (`pkgbuild_audit`) was build-time-only and undiscoverable; now any **AUR** package's detail
  page has a **"Build recipe" → View PKGBUILD** button (AUR-only; repo pkgs are built+signed by Arch,
  Flatpak/AppImage have none) opening a dedicated `#pkgbuild-modal`: a **sticky risk summary**
  (scan counts + the never-a-safety-check disclaimer), a **metadata panel** (maintainer/contributors/
  pkgver/upstream + source URLs + checksum status incl. ⚠ SKIP), **line-linked findings** (click →
  scroll+flash the line), and the **full syntax-highlighted, line-numbered PKGBUILD** (a light pure
  regex bash highlighter — comments/strings/keywords/vars; no external lib, WebKitGTK/offline).
  Backend: pure `pkgbuild.parse_metadata(text)`; `arch` controller `fetch_pkgbuild(base, commit=None)`
  (extracted from `_fetch_pkgbuild_at_commit`, HEAD when no commit) so the cgit URL lives in the gem;
  `AtlasApi.get_pkgbuild(pkg_id)` resolves the package **base** via `aur_client.get_info` →
  `PackageBase`, fetches the current published PKGBUILD, scans + parses, and **fails open** (any
  failure → `{}`; advisory, never a gate). Frontend builders all pure + Node-VM-tested
  (`highlightBashLine`, `buildPkgbuildRiskHTML/MetaHTML/FindingsHTML/CodeHTML`). Tests:
  `test_pkgbuild_meta.py` (6), `test_api.py::PkgbuildViewTest` (4), `main_js_contracts`
  (`testPkgbuildViewerBuilders`). Suite **516** + JS **38**. **Needs a GUI eyeball** (open an AUR
  pkg → View PKGBUILD; risk banner tone, metadata, click a finding → scroll, highlighting; verify a
  non-AUR pkg shows no button; offline → friendly empty state). **Deferred to increment 2:** `.install`
  scriptlet tab, anchored "changed since last build" diff, copy-raw button. Plan:
  [plans/2026-06-05-pkgbuild-viewer.md](plans/2026-06-05-pkgbuild-viewer.md).
  **Increment 2 (2026-06-05, GUI-verified increment 1):** (a) a **"View PKGBUILD" button in the
  install transaction preview** (AUR-only, via `source_label`) — the viewer is now reachable at the
  actual review-before-build moment, not just the detail page (viewer `z-index` lifted above the other
  modals so it stacks on top when opened from the preview); (b) a **`.install` scriptlet tab** —
  `get_pkgbuild` resolves `install=` filename(s) via pure `pkgbuild.parse_install_files` (expands
  `$pkgname`/`$pkgbase`/`$_*`), fetches each via the generalised `fetch_aur_file`, scans them, and
  returns a `files` list (PKGBUILD first); the viewer shows a tab bar (`buildPkgbuildTabsHTML`, warn-
  count badges) when >1 file, and the **risk summary is now combined** across PKGBUILD + scriptlets;
  (c) a header **Copy** button (active file → clipboard). Tests: `test_pkgbuild_meta.py::ParseInstallFilesTest`
  (7) + `PkgbuildViewTest` (+2) + `testPkgbuildViewerBuilders` tabs assertions. Suite **525** + JS 38.
  **Needs a GUI eyeball** (open an AUR pkg with an `.install`, e.g. `visual-studio-code-bin` → tab + badge;
  Copy; combined risk count).
  **Increment 3 (2026-06-05) — "changed since your build" diff (theme complete):** for an *installed*
  AUR package whose built `commit` we cached, `get_pkgbuild` fetches the PKGBUILD at that commit and
  `diff_lines`s it against the current published one; returned as `data.diff`. The viewer is now a
  list of **views** (pure `buildPkgbuildViews`): a **"Changed since your build" diff tab leads**
  (accent badge = add/del count) when present, then PKGBUILD + `.install`; diff rendered by pure
  `buildPkgbuildDiffHTML` (reuses the build-time review's `.diff-line` markup). Best-effort (no
  baseline / unchanged / fetch fail → no diff tab). Tests: `PkgbuildViewTest` (+3) + view/diff JS
  assertions. Suite **528** + JS 38. **Needs a GUI eyeball** on an installed-but-behind AUR pkg (the
  diff tab leads + colored). *Test gotcha:* `noDiffViews` is built inside the JS-harness vm sandbox
  (a different realm) so `assert.deepStrictEqual` fails its prototype check — compare via
  `JSON.stringify` for sandbox-created arrays/objects.
- **"Why is this installed?" — install reason + orphan status (2026-06-05).** Folded into the
  dependency summary (its natural home — required-by was already there). For an **installed** package,
  `get_dependency_summary` now also returns `install_reason` (`explicit`/`dependency`/`None`) + a
  derived `orphan` flag, via a new pure `pacman.get_install_reason(name)` that parses the local
  `pacman -Qi` "Install Reason" line (`orphan = dependency && nothing requires it`). The detail section
  leads with a one-line banner: "You installed this explicitly." / "Installed as a dependency of other
  packages." / (amber) "…an orphan you can likely remove." Answers the BACKLOG "Why is this installed?"
  item. Tests: `test_pacman_info.py::GetInstallReasonTest` (3) + `DependencySummaryTest` orphan/explicit
  + JS assertions. Suite **506** + JS 37. Plan:
  [plans/2026-06-05-better-detail-pages.md](plans/2026-06-05-better-detail-pages.md).
  **Polish (2026-06-05, GUI-eyeball follow-up):** gave every `.detail-section` a 28px top margin (the
  "Details" heading was hugging the dependency note), and suppressed the now-redundant `dependson` /
  `optdepends` / `orphan` rows from the get_info Details table (the Dependencies section renders them
  better; makedepends/checkdepends are build-only and kept). Also dropped the **`maintainer`** Details
  row: for Arch its value is just the source string (`aur` / a repo name), not a person — it
  contradicted the header, which shows the real maintainer (e.g. `dcelasun`) + the source badge.
- **Better app detail pages — "why this source?" + dependency summary (2026-06-05).** Two additions to
  the detail modal serving Atlas's multi-source-honesty angle (the BACKLOG "Better app detail pages"
  item; the source-compare panel + transaction preview already shipped). (1) **"Why this source?" hint**
  — an honest one-line trust note under the header, pure `whySourceHint(type, {verified, free_license})`
  → `{text, level}`: official-repo (signed by Arch) / AUR (community, review the PKGBUILD) / Flatpak
  (verified-vs-community + FOSS/proprietary, refined when Flathub metadata arrives) / AppImage
  (not sandboxed). The single-source counterpart to the compare panel's `sourceCompareNote`. (2)
  **Dependency summary** — a compact **Dependencies** section: Requires (direct) / Optional /
  Required-by counts, each an expandable chip list, via one cheap `AtlasApi.get_dependency_summary`
  reusing the preview's pacman/AUR signals (`map_updates_data` `d` / `map_optional_deps` /
  `map_required_by`; AUR `get_info` Depends+OptDepends) and **failing open per field**. Reverse deps
  only queried when installed; Flatpak has no pacman-style deps → empty + a note (we don't fake it).
  Both lazy + stale-guarded by `stillCurrentDetail()`. Tests: `test_api.py::DependencySummaryTest` (6) +
  JS `whySourceHint`/`buildDependencySummaryHTML` contracts (2). Suite **502** + JS **37**. **Needs a
  GUI eyeball** (hint per source; dep counts + expand on a repo pkg / AUR pkg / Flatpak). Plan:
  [plans/2026-06-05-better-detail-pages.md](plans/2026-06-05-better-detail-pages.md).
- **Fix: test polluting the real activity log (2026-06-05).** `test_import_packages_install_success`
  exercised the real `import_packages` → `record_activity` without patching it, so every test run
  appended a bogus `missing-pkg (Flatpak)` install row to the user's
  `~/.cache/atlaspm/activity.jsonl` (226 had accumulated, flooding the new Activity page). Patched
  `record_activity` in that test (+ asserted it's called with `('install','missing-pkg','Flatpak',True)`);
  verified the log no longer grows across a full suite run. Cleaned the 226 junk rows from the local
  log (backup kept), preserving the 110 real entries. **Gotcha for future tests:** any test that
  drives an install/uninstall/update/downgrade/import/batch path must patch
  `atlas.view.webview.api.record_activity` (the others already do).
- **History / rollback center — increment 2: pacman-log links (2026-06-05).** Arch/AUR activity
  entries now carry a **"pacman log"** disclosure: first expand lazily fetches
  `AtlasApi.get_pacman_log(pkg_name)` and lists the matching `/var/log/pacman.log` lines (action
  verb + version token + timestamp, newest first). Backend = a pure
  `parse_pacman_log(text, pkg_name, limit=20)` (exact-name match on ALPM
  `installed|upgraded|downgraded|removed|reinstalled` lines; upgrades keep the `old -> new` token)
  + a thin reader that **fails open** (missing/unreadable/non-Arch → empty; the log is
  world-readable, so no root). Flatpak entries don't get it (pacman doesn't record them). Tests:
  `test_api.py::ParsePacmanLogTest` (3) + JS assertions (`activityHasPacmanLog`,
  `renderPacmanLogLine`). Suite **496** + JS 35. **Needs a GUI eyeball.** Plan:
  [plans/2026-06-05-history-rollback-center.md](plans/2026-06-05-history-rollback-center.md).
- **History / rollback center — increment 1 (2026-06-05).** Turned the flat Activity feed into a
  usable history page (the BACKLOG "History / rollback center" item). **Frontend-heavy, low risk**
  (one backend line): `get_activity` now reads up to 200 entries (was 50) since filtering is
  client-side. New pure helpers (Node-VM-tested): `filterActivity(entries,{action,type,query})`
  (composing, case-insensitive), `groupActivityByDate` (Today / Yesterday / Earlier this week /
  Older; invalid timestamps → Older, never throws), `activityEntryActions` (which rollback button
  an entry gets), `activityActionsPresent`/`activityTypesPresent` (filter-option discovery). The
  page now has a **filter bar** (action chips + source-type select + name search — all re-render
  from the cached entries, no refetch) and **date-grouped sections**. Each entry got **rollback
  affordances** that reuse the existing safe flows: **Downgrade** on a successful Arch/AUR/Flatpak
  install/update/downgrade (`downgradeApp(id)`), **Reinstall** on an uninstall (`installApp(id)`),
  and a clickable package name that **searches** for it (the "view" path — the live card shows
  accurate state). Affordances reconstruct the `{type}:{name}` id and route through the normal
  preview → root-password → terminal flow (`_get_pkg` self-heals by search), so they're honest
  entry points, not guarantees. Tests: `main_js_contracts::testActivityFilterGroupAndActions`.
  Suite **493** + JS **35**. **Needs a GUI eyeball** (filters compose, date groups render,
  Downgrade/Reinstall route through the preview, name-search navigates). **Deferred** to later
  increments: log clear/export. Plan:
  [plans/2026-06-05-history-rollback-center.md](plans/2026-06-05-history-rollback-center.md).
  **Polish (2026-06-05, GUI-eyeball follow-up):** the `update_all` filter chip + per-entry chip now
  show friendly labels ("Update All", underscores→spaces); failed-entry errors no longer dump the
  raw stringified pywebview JS-error object — a new pure `cleanActivityError` pulls out just the
  `message` (stack/line stripped), truncates, and the line is single-line/ellipsised. JS asserts added.

- **Terminal polish — outcome-colored bar + "completed with warnings" state (2026-06-05, GUI-eyeball follow-up).**
  Two issues a GUI check surfaced. (1) **Progress bar never settled** — on done it stayed at whatever width
  it reached and was always green; now `terminalSetDone` fills it to 100% tinted by outcome (green success /
  **amber warned** / red failure) and `terminalOpen` resets width + color for the next run. Also dropped a
  doubled divider between the activity line and the "Raw output" toggle (both carried a 1px border →
  removed the toggle's `border-top`). (2) **A failed *optional* dependency reported a bare green "Success"**
  despite a scary `ERROR: Build failed` in the log (repro: `visual-studio-code-bin` + optdep `icu69`, whose
  `check()` fails on Python 3.13). **Traced it end-to-end:** the success flag propagates faithfully — every
  *hard* dep/makedep failure aborts (`_handle_missing_deps` → False), and `makechrootpkg` `die`s with exit 1
  on a build failure. The **only** path where "Build failed" coexists with overall success is the *optional*
  dep path: `_install_optdeps` (and `_build`'s try/except around it) deliberately swallow optdep failures —
  optdeps are non-fatal, so the main package genuinely installed. The bug was honesty of presentation, not
  correctness. Fix (the chosen "amber partial state"): `TransactionContext.warnings` collects an advisory when
  an optdep build fails (`arch.install.optdep.warning[.generic]`); `install()` surfaces them via the new
  `TransactionResult.warnings` field (shared contract, optional, gem-agnostic); `AtlasApi.install` passes them
  to `terminalSetDone(success, warnings)`; the frontend shows an **amber "Completed with warnings"** status +
  done message + an amber notice card naming the failed optdep(s), while the bar goes amber (not green). Other
  paths/gems unaffected (warnings defaults to None). Tests: `main_js_contracts::testTerminalDoneWarnedState`
  (amber state + plain-success stays green). Suite **493** + JS **34**. **GUI-verified 2026-06-05** (bar color +
  divider fix + amber warnings state all eyeballed).
- **Terminal polish — activity line + friendly failure summary (2026-06-05).** The terminal panel
  (live + final view of a transaction) is no longer a raw-log wall — it closes the operation-confidence
  loop the pre-flight preview opened. **Frontend-only** (the watcher already pushes
  status/substatus/append/done): (1) **Current-activity line** — a spinner + the latest meaningful
  message, picked by a pure `pickActivityText` (substatus → status → last log line → "Working…", never
  blank). (2) **Collapse/expand raw output**; (3) **Copy full log** (header button → clipboard);
  (4) **Friendly failure summary** — on failure a card names the likely cause + next step via a pure
  ordered `summarizeFailure(log)` (auth → PGP/keyring → download/404 → file conflict → package conflict
  → dependency → build → generic); advisory, raw log stays below.
  **Design note (GUI eyeball):** a discrete **step timeline was attempted and dropped** — gems don't
  emit clean phase events (`change_status` is barely used; Flatpak blanks the substatus and only
  `print`s), so the stepper was empty for most operations. The always-populated activity line is the
  honest replacement.
  **Also fixed:** gem status/substatus carried HTML (`bold()` → `<span style=…>`) that leaked as literal
  text; `WebviewWatcher.change_status`/`change_substatus` now run the existing `_clean` tag-stripper —
  **`print` (raw log) stays verbatim** (legit angle brackets: C++ templates, redirects). Tests:
  `main_js_contracts` (`summarizeFailure`, `pickActivityText`) + `test_watcher.py::WatcherStatusCleaningTest`
  (3). Suite **493** + JS **31**. **Needs a GUI eyeball.** Plan:
  [plans/2026-06-05-transaction-timeline.md](plans/2026-06-05-transaction-timeline.md).
  **Follow-ups (2026-06-05):** (a) fixed a leftover `substatusEl` reference that crashed `terminalOpen`
  (ReferenceError on every install) + added `testTerminalFlowRunsWithoutError` (drives the real
  handlers in the DOM harness, catching this class of bug). (b) Some tools (Flatpak/OSTree) `print` a
  **textual progress bar** out of block glyphs; the activity line now strips those (`stripProgressBar`,
  raw log stays verbatim) and parses the `%` to drive the real progress bar (`extractPercent`). JS 33.
- **Fix: misleading category chip counts (2026-06-05).** Category chips showed a package count
  (e.g. "Office · 1 package") computed from `categories.txt` (the **Arch-repo index only**), but
  opening a category also lists Flathub apps — so the number understated reality (Office → 1 shown,
  ~40 on open). Accurate combined counts would need a Flathub network call per category on every
  Browse open (the count path is deliberately cheap/no-network). Fix: **drop the count from category
  chips** (label only); the **AUR buckets keep their count** (those are exactly the curated top-60 we
  show, so it's truthful). Frontend-only.
- **GUI polish — Browse chips + card-action alignment (2026-06-05, GUI eyeball follow-up).** (1) **Card
  action buttons** (Pin/Install/Uninstall/Update) jumped between bottom-right and bottom-left across
  cards — the footer is `space-between` + `flex-wrap`, so a wide vote badge or the longer "Uninstall"
  label wrapped the action group to a left-aligned second line on some cards. Now
  `.package-footer > div:last-child { margin-left: auto }` keeps the group **bottom-right consistently**,
  wrapped or not. (Affects all package cards.) (2) **Browse landing chips:** unified the category row
  and the AUR discovery row onto one **compact left-packed chip** style (`.browse-chip` + icon/label/
  count; `.browse-chip-aur` adds the community accent) — the big category tiles are gone, both rows now
  match and don't leave half-empty grid lines. (3) Both section headers now carry a **scope note**:
  "Browse by category · *official repos & Flatpak*" and "Discover on the AUR · *community-maintained*".
  CSS/markup only; suites green (490 + 29, one contract assertion updated to the new markup).
- **AUR discovery buckets (2026-06-05).** Browse now offers AUR **discovery buckets** — the feasible
  alternative to (impossible) AUR categories: **Popular**, **Recently updated**, **VCS (-git)**,
  **Binary (-bin)**, shown as a distinct "Discover on the AUR" row under the official categories.
  **Data-source decision** (made with the user): the buckets need votes/popularity/dates the names
  index lacks and the RPC has no browse-all endpoint, so they're **precomputed in the `atlas-files`
  repo** (same pattern as suggestions/categories): a new `arch/generate_aur_discovery.py` downloads
  the `packages-meta-ext-v1.json.gz` dump and writes a small `arch/aur_discovery.json` (top 60/bucket,
  RPC-shaped entries), refreshed daily by `.github/workflows/aur-discovery.yml`. Atlas fetches that
  JSON (1 h in-memory TTL, fails open) via `AtlasApi.get_aur_discovery()` (landing buckets) +
  `get_aur_bucket_packages(key)`; the arch gem's new `list_aur_packages(entries)` maps the entries to
  real `ArchPackage` objects through the **existing `AURDataMapper`** (so install/detail/preview all
  work). Frontend: `renderBrowse` renders the bucket row; `renderCategoryPackages(key,label,{api})`
  generalised so a bucket reuses the category list/back/topbar machinery. Tests:
  `test_api.py::AurDiscoveryTest` (7: nonempty-bucket listing, cache, fail-open, mapping, unknown key).
  Suite **490** + JS 29. **Live:** atlas-files pushed (`9e0245f`) and the raw URL serves the JSON
  (HTTP 200, ~93 KB) — the GH Action will refresh it daily. **Installed-state on cards (follow-up,
  same day):** `list_aur_packages` now does one cheap `pacman -Q` (`pacman.map_installed`, not the slow
  `read_installed`) and threads the result through `map_api_data`'s `pkgs_installed` path, so bucket
  cards read **Install / Uninstall / Update** correctly (Update via `check_version_update` on installed
  vs AUR version). Fail-open (pacman error → nothing marked installed). Test:
  `tests/gems/arch/test_aur_discovery.py` (3). **Needs a GUI eyeball.** Plan:
  [plans/2026-06-05-aur-discovery-buckets.md](plans/2026-06-05-aur-discovery-buckets.md).
- **Transaction preview — increment 4: source-comparison panel (2026-06-04, theme complete).** When an
  app is offered by **more than one source** (e.g. Steam from the Arch repo + Flathub), its detail page
  now shows a compact "pick where to install from" table above the description: one row per source with
  source pill, version, size, a one-line characterisation (`sourceCompareNote`), and an **Install**
  button per non-installed source ("✓ Installed" on the one you have). Pure `buildSourceCompareHTML(group)`
  built **entirely from the in-memory group** the grid already collapsed (`collapseByName`) — **no extra
  backend calls**; each Install routes through the normal `installApp` (and thus the full transaction
  preview), so the panel is the fast chooser and the preview the deep-dive. `openDetailModal(pkg, group)`
  gained an optional group (card clicks pass it; else `findGroupForPkgId` looks it up); single-source
  apps render nothing. Test: `main_js_contracts::testBuildSourceCompareHTML`. Suite 480 + JS **29**.
  **Needs a GUI eyeball.** This **completes the universal transaction-preview theme.** Plan:
  [plans/2026-06-04-transaction-preview.md](plans/2026-06-04-transaction-preview.md).
- **Transaction preview — increment 3: update + Update-All aggregate (2026-06-04).** The pre-flight
  preview now also gates **single-package updates** and the **Update-All** bulk upgrade. *Single
  update* (`get_update_preview`): an update is an acquire of a newer version, so it reuses the install
  assembler (extracted as `_assemble_acquire_preview`) + adds `from_version`; the header renders
  **`v{old} → v{new}`** and the same per-source advisories as install. *Update-All aggregate*
  (`action='update-all'`): **frontend-assembled** by the pure `buildUpdateAllPreviewData(updates,
  extras)` from the **already-loaded** updates list — **no extra `read_installed`** (the slow call) —
  showing package count, per-source split (Arch/AUR/Flatpak), total download size (AUR excluded — built
  from source, noted), and folding the cheap `check_upgrade_news` + `get_pacnew_files` counts in as
  warnings. Reuses the one modal/renderer via a synthesised payload. The **rich Arch news gate is
  kept** and fires *after* the aggregate (aggregate = the "what", news gate = the clickable articles to
  read first); cancel at either stage aborts cleanly. Tests: `test_api.py::UpdatePreviewTest` (3) +
  `main_js_contracts` (+2: version delta, aggregate builder). Suite **480** + JS **28**. **Needs a GUI
  eyeball.** Plan: [plans/2026-06-04-transaction-preview.md](plans/2026-06-04-transaction-preview.md).
- **Transaction preview — increment 2: uninstall + downgrade (2026-06-04).** The pre-flight
  "here's what this will do — proceed?" modal now also gates **uninstall** and **downgrade** (it
  already gated install). Same payload shape + a new `action` field; the modal title, description,
  proceed-button label/colour, and size-row label key off it (one modal, one renderer). **Uninstall**
  (`get_uninstall_preview`/`_preview_uninstall_arch`): reverse dependencies via
  `pacman.map_required_by` → a **danger** warning listing the installed packages that depend on it
  (truncated to 12), or a reassuring note when nothing does; **freed space** from
  `pacman.get_installed_size` (rendered as "Frees"); an orphan-cleanup note; Flatpak shows freed size
  + a runtime-reclaim note. **Downgrade** (`get_downgrade_preview`): advisory only (the gem picks the
  target version interactively, not cheaply knowable up front) — a **warn** ("rolling back can
  reintroduce fixed bugs/security issues") + notes ("you'll pick the version next", "deps aren't
  downgraded", AUR rebuilds from previous source). Honest scope unchanged: no second resolver,
  **fail-open per field**, never blocks. Frontend: `installApp`/`uninstallApp`/`downgradeApp` all await
  a shared `showTransactionPreview(id, action)` (generalised from `showInstallPreview`, kept as a thin
  wrapper); cancel aborts cleanly. Tests: `test_api.py::UninstallPreviewTest` (5) + `DowngradePreviewTest`
  (3) + install action assertion; `main_js_contracts` (+2: action labels, action copy). Suite **477** +
  JS **26**. **Needs a GUI eyeball** (uninstall a pkg with dependents → danger list; downgrade → advisory;
  confirm proceeds, cancel aborts). Plan: [plans/2026-06-04-transaction-preview.md](plans/2026-06-04-transaction-preview.md).
- **Transaction preview — notice/permission icon polish (2026-06-04).** GUI-eyeball follow-up to
  increment 1: the preview's permission rows and top notices now lead with the same colored circular
  icon chip as the Flathub info-popup (reusing `getPermissionIcon` + new `getWarningIcon`, mapping
  titles→glyphs; `rich-badge-icon` + `perm-icon-{danger,warn,info,safe}` classes). Dropped the old
  left-accent stripe on notices in favour of a **subtle severity-tinted background wash** (`.txp-warn-*`,
  `rgba(...,.10)`); permission rows keep an **uncolored** background. Frontend/CSS only; JS contracts +
  webview suite green (139). GUI-verified.
- **Transaction preview — increment 1: Install (2026-06-04).** A pre-flight "here's what this will
  do — proceed?" modal now gates **installs** (before anything privileged runs). Backend
  `AtlasApi.get_install_preview(pkg_id)` assembles a per-source payload — `{name, source,
  source_label, version, sizes:{download,installed}|None, deps:{direct,optional}, permissions|None,
  warnings:[{level,title,detail}], notes}` — **reusing existing signals**, not re-implementing the
  resolver: repo → one `pacman.map_updates_data` (`-Si`: version/sizes/**direct** depends) +
  `map_optional_deps`; AUR → `aur_client.get_info` (version/maintainer/depends/makedepends/out-of-date,
  **no size** — built from source) + community/maintainer-change/orphaned/out-of-date warnings;
  Flatpak → `get_flathub_metadata` (permissions list + advisory safety tier + proprietary/unverified
  warnings). **Fails open per field** (failed probe → None/[] + a note; a top-level failure still
  returns a minimal `ok` payload) so it never blocks an install. Honest scope: deps shown are
  **direct** only, labelled "pacman/makepkg resolves the full set at install time" — no second
  resolver. Frontend: pure `buildTransactionPreviewHTML` (header / size row / severity-sorted
  warnings / permissions + deps accordions / notes, Node-VM-tested) + a promise-based
  `#tx-preview-modal` mirroring the news gate; `installApp` awaits it first, cancel aborts cleanly.
  One gate covers both card and detail-modal installs (both route through `installApp`). The existing
  **mid-build AUR PKGBUILD confirmation is kept** (it sees the post-edit text; preview is
  advisory-before — complementary). Tests: `test_api.py::InstallPreviewTest` (5) +
  `main_js_contracts` (3). Suite **468** + JS harness **22**. **Needs a GUI eyeball** (repo / AUR /
  Flatpak install → preview renders; confirm proceeds, cancel aborts). Next increments:
  update/uninstall/downgrade + Update-All aggregate, then the source-comparison panel UI. Plan:
  [plans/2026-06-04-transaction-preview.md](plans/2026-06-04-transaction-preview.md).
- **`.pacnew` center + mirror polish + no-flash view renders (2026-06-04).** Finished the Arch
  cockpit. **`.pacnew` center**: a reviewable sub-view (reached from the System Health "Config files"
  card + the Updates notice; `currentView='pacnew'`, no nav item) listing each file with a **risk
  badge** (pure `pacnewRisk`: mirrorlist→danger "regenerate, don't overwrite"; pacman.conf/sudoers/
  fstab/…→warn; else info), a read-only **Show diff** (backend `get_pacnew_diff`: `diff -u` of the
  installed file vs its `.pacnew`, whitelisted to the real list, no root, truncated; root-only →
  "use pacdiff"), and **Copy path**; global **Open pacdiff** + **Regenerate mirror list**. No
  auto-merge. **Mirror polish**: Settings → Mirrors shows an active-mirror summary (count + top hosts
  + last-updated) and previews the exact regen command, via `get_mirror_status()`; refreshes after a
  regen. **No-flash renders**: a `navEpoch` bumped per navigation + a delayed `pendingSpinner` make
  the async utility renderers (News/Permissions/Settings/Activity/Disk/Browse/Health/pacnew) keep the
  prior view until the new one is ready and bail if superseded — fixes the stale-render bug (switch
  away mid-load) **and** the rapid-switch flash. Tests: `test_api.py::PacnewMirrorTest` (4) +
  `main_js_contracts` (pacnewRisk, stale-render). **GUI-verified.** Suite 463 + JS harness 19. Plans:
  [plans/2026-06-04-pacnew-center-mirror-polish.md](plans/2026-06-04-pacnew-center-mirror-polish.md).
- **System Health page — the "Arch cockpit" (2026-06-04).** New **Health** sidebar page:
  package-management health checks, each card = status pill + explanation + one safe action.
  Checks: database sync age, mirror list, pacman lock, `.pacnew` files, orphan packages, package
  cache, unused Flatpak runtimes, AUR clean-chroot — actions reuse existing handlers (Open Updates /
  regenerate mirrors / pacdiff / orphan checklist / clean cache / remove unused / Settings).
  Backend `AtlasApi.get_system_health()` runs the cheap signals concurrently + fails open per field;
  pure `systemHealthChecks(data)` maps to toned cards (Node-VM-tested). **GUI-verified.** Also fixed a
  latent bug it surfaced: post-operation paths (terminal-close, refresh button, import) called
  `fetchPackages()`, which on a utility view fell through to app suggestions — new
  `refreshCurrentView()` re-renders the active view instead (regression-tested). Suite 459 + JS
  harness 17. Plan: [plans/2026-06-04-system-health.md](plans/2026-06-04-system-health.md).
- **GUI polish trio — density / contextual topbar / unified empty states (2026-06-04).** Three
  frontend-only items, **GUI-verified**: (1) **Display density** (Comfortable/Compact/Dense) — a
  `localStorage` pref applied app-wide via a `body.density-*` class; Settings → General select applies
  it instantly (no Save). (2) **Contextual topbar** — the package-list controls (type filter / sort /
  view-toggle / Select) show only on Installed/Updates, an open Browse category, or any view with an
  active search; hidden on the dashboard, Browse landing, and utility pages
  (`shouldShowPackageControls` + `applyTopbarContext`). (3) **Unified empty/error states** — a shared
  `emptyStateHTML({icon,title,hint,action})` replacing the inconsistent plain-text empties on News,
  Browse categories, category packages, Permissions (action → Browse), and Activity; offline vs
  genuinely-empty wording. Pure helpers (`densityClass`/`shouldShowPackageControls`/`emptyStateHTML`)
  Node-VM-tested. Suite 456 + JS harness 15. Plan:
  [plans/2026-06-04-gui-polish-small.md](plans/2026-06-04-gui-polish-small.md).
- **Command palette (Ctrl+K) (2026-06-04).** A keyboard-first launcher: **Ctrl+K**/**Ctrl+P** opens a
  filterable overlay (`#command-palette`); **fuzzy** subsequence match on label + keywords (`fuzzyScore`,
  best-first), ↑/↓ to move, Enter/click to run, Esc to close. Commands = navigation to every page +
  actions reusing existing handlers (update all, clean orphans, refresh, grid/list, select mode,
  regenerate mirrors, open pacdiff, export manifest, focus search). Update-all / clean-orphans are
  gated on their topbar buttons being visible (`available()`); commands with a global shortcut show it
  as `<kbd>` badges. Registry/scorer/filter are pure (`buildCommandList`/`fuzzyScore`/`filterCommands`,
  Node-VM-tested); open/render/keyboard-nav are DOM-bound. **GUI-verified 2026-06-04.** Frontend-only.
  Plan: [plans/2026-06-04-command-palette.md](plans/2026-06-04-command-palette.md).
- **Dashboard "Attention Center" (2026-06-04).** The dashboard now shows a row of lazy, best-effort
  cards above the suggestions grid answering "what needs my attention today?": **Updates** (count +
  Arch/AUR/Flatpak split, "up to date" at 0), **System safety** (`.pacnew` count, DB-sync age, pacman
  lock, unread news since sync), **Reclaim space** (orphans, pacman cache size, unused Flatpak
  runtimes), **Recent activity** (last 3), **AUR safety** (chroot enabled/available). Each card
  click-throughs to the page that acts on it. **The dashboard is the Attention Center only** — the
  app-suggestions grid was removed from it and **moved to Browse** as a "Suggested for you" row above
  the categories (discovery now lives in Browse + Installed + search). Card tone is a tinted circular
  icon chip (not a side stripe), and the grid shares `.packages-grid`'s 24px inset. Backend:
  `AtlasApi.get_dashboard_summary()` runs the
  cheap signals concurrently on the shared executor and **fails open per field** (a failed check →
  None / "couldn't check"), reusing `get_pacnew_files`/`check_upgrade_news`/`get_cleanup_summary`/
  `get_activity` + `_last_db_sync_time` + the arch chroot config. **Updates are excluded from that
  payload** (they need `read_installed`); the frontend fetches `get_updates` separately and **shares
  the Updates view's `packageCache`** (warm-reuse both ways → one read_installed). Frontend: pure HTML
  builders (`buildAttentionCenterHTML`/`buildUpdatesCardHTML`, unit-tested in the Node VM harness) +
  `renderAttentionCenter` with a stale-render epoch guard; `#attention-center` cleared on non-dashboard
  views. Tests: `test_api.py::DashboardSummaryTest` (3, incl. fail-open) + `main_js_contracts.test.js`
  suite 456 + JS harness 11. **GUI-verified 2026-06-04**: greeting + tone-colored status line, hero
  cards, click-through, the **Display-name** setting (Settings → General → custom greeting name), and on
  Browse the categories-on-top + Flatpak "Suggested" row + color category icons (💻/⚙️).
  Deferred: a Flatpak-permissions "risky apps" card (needs expensive per-app reads). Plan:
  [plans/2026-06-04-dashboard-attention-center.md](plans/2026-06-04-dashboard-attention-center.md).
- **Release 0.11.0 — prep (2026-06-04).** `__version__` had read `0.10.7` since the initial commit
  (the bauh fork point, never bumped); everything Atlas accumulated on top of it. Bumped
  `atlas/__init__.py` → **0.11.0** (flows to the About dialog, `--version`, `pyproject`/`setup`,
  and the PKGBUILD `pkgver()`), updated the README status line + the PKGBUILD/.SRCINFO `pkgver`
  placeholders, and added a curated **`CHANGELOG.md`** `0.11.0` section (prepended above the
  inherited bauh history; theme-grouped, not a commit dump). Verified: wheel builds
  `atlas-0.11.0-py3-none-any.whl` (`python -m build --wheel --no-isolation`); suite 451 green.
  Tagged `v0.11.0` locally. **AUR publish NOT done** — it's outward-facing; run
  `linux_dist/arch/publish-aur.sh` (or `--dry-run`) to push `atlas-pm-git` when ready (for a
  `-git` pkg it only matters when PKGBUILD/.SRCINFO content changes). Plan:
  [plans/2026-06-04-release-0.11.0.md](plans/2026-06-04-release-0.11.0.md).
- **Browse — Flatpak categories (sprint 2, 2026-06-04).** Browse-by-category was Arch-repo-only;
  it now also lists **Flathub** apps per bucket. New pure mappers in
  `atlas/gems/flatpak/flathub.py`: `map_collection_hit` (flattens one
  `/api/v2/collection/category/<Cat>` hit — uses the **dotted `app_id`**, not the underscore-joined
  `id`) + `collection_apps` (one best-effort HTTP call, `[]` on any miss → never blocks Browse).
  `FlatpakManager.list_category_packages(category)` builds non-installed `FlatpakApplication` cards
  from it (icon/name/summary set; webview lazy-loader fills the rest). `CATEGORY_BUCKETS` gained a
  5th element = the matching Flathub category; `AtlasApi.get_category_packages` now concatenates Arch
  + Flatpak results (gated on the gem being enabled + `can_work`), and the frontend's existing
  `collapseByName()` merges same-named Arch+Flatpak pairs into one multi-source card — **no frontend
  change needed**. `get_categories` counts stay Arch-only/cheap (no per-bucket network on Browse
  open). **AUR deliberately excluded** — the RPC has no category source (see Next). Tests:
  `test_flathub.py` (+4), `test_api.py::BrowseCategoryTest` (+2). **Needs a GUI eyeball.** Plan:
  [plans/2026-06-04-polish-tail.md](plans/2026-06-04-polish-tail.md).
- **Installed-app icons — search the active icon theme (sprint 2, 2026-06-04).** `_resolve_installed_icon`
  only searched `hicolor/*` + `pixmaps`, so theme-only icons fell back to a letter avatar. Now
  `_find_icon_file` searches the **active icon theme** + its `Inherits` chain first. All
  filesystem/subprocess, **thread-safe (no `Gtk.IconTheme`)**: `_active_icon_theme` reads the theme
  name (`gsettings` → `~/.config/gtk-3.0/settings.ini` → `hicolor`); `_theme_app_dirs` parses each
  theme's `index.theme` `Directories=`, keeps Applications-context dirs ordered scalable-first then
  largest size, recurses `Inherits=` across `~/.local/share/icons` / `~/.icons` / `/usr/share/icons`
  (parse, not a full FS walk); results cached for the session. Falls back to the old hicolor/pixmaps
  list. Tests: `test_api.py::InstalledIconResolveTest` (+3, incl. inherits chain + scalable ordering +
  settings.ini fallback). **Needs a GUI eyeball.** Plan:
  [plans/2026-06-04-polish-tail.md](plans/2026-06-04-polish-tail.md).
- **Webview polish sprint 1 (2026-06-03).** Added a pytest-driven Node VM contract harness for
  `atlas/view/webview/main.js` and fixed the first polish batch: Browse category results now populate
  `currentPackages` so cards/details/select logic work; sort/type filter re-render an open Browse
  category in-place while the top-level Browse grid stays categories; top-level Browse refresh/clear
  search routes back to categories instead of dashboard suggestions; detail-modal async icon/meta/info/
  screenshot/history callbacks ignore stale package IDs; package-list fetches use an epoch guard so
  older search/view responses cannot repaint newer results. Plan + manual smoke checklist:
  [plans/2026-06-03-webview-polish-sprint-1.md](plans/2026-06-03-webview-polish-sprint-1.md).
  Verification: `python -m pytest tests/view/webview -q` → 117 passed; `python -m pytest` → 442 passed;
  user GUI-eyeballed Browse sprint-1 flow, downgrade, and screenshot lightbox and reported they look good.

- **Documentation truth pass (2026-06-03).** Reconciled the docs with the current pure-Python,
  pywebview Atlas state: rewrote `docs/ARCHITECTURE.md` to remove live Rust/PyO3/native-extension
  instructions and document the actual layers/product flows; refreshed README roadmap to mark rich
  details, Browse, tray, chroot builds, AUR safety, and Flatpak permissions as shipped; updated
  `AGENTS.md`/`GEMINI.md` so STATUS/BACKLOG are the active planning docs and ROADMAP is historical;
  converted `benchmarks/README.md` into a historical benchmark note instead of dead Cargo build
  instructions; fixed the ROADMAP cross-link that pointed at the removed Python↔Rust architecture
  section. Verification: local Markdown links OK; suite 441 tests green.

- **Detail screenshots & lightbox polish (2026-06-03).** Polished the screenshots gallery and fullscreen lightbox viewer: (1) **Centering**: centered thumbnails inside the flex container using `justify-content: safe center` to support scrolling on overflow. (2) **Scrollbars**: added custom WebKit scrollbar styling. (3) **Aesthetics**: increased border radius (`var(--radius-md)`), added shadow depth, and designed an active hover state (slight scale up, border color transition, and glow). (4) **Lightbox**: added a smooth scale-up entry animation (`lightboxScaleUp`), increased shadow, added a glassmorphic background/border to navigation/close controls, and improved active hover transforms.

- **Fix: uninstalled AUR packages showing "Changed Maintainer" (2026-06-03).** Uninstalled packages showed a maintainer change warning (e.g. "Changed Maintainer: aur -> dcelasun") when viewed in details. Fix: restrict `changed` maintainer advisory check in `get_aur_meta` to installed packages only. Tests: added `test_uninstalled_never_flags_maintainer_change` to `test_api.py`. Suite 441 tests green.

- **Bazaar/Flathub inline header metadata (2026-06-03).** The detail modal's header was redesigned to match Bazaar and Flathub: the package type (e.g. Flatpak, AUR) is now a standalone pill next to the application title. The subtitle area dynamically populates with the developer/maintainer name, a clickable verified/unverified icon badge, and the application version. This cleans up the rich badges grid by moving publisher details into the header. Also implemented deferred meta lazy loading (`IntersectionObserver`) with a 300ms debounce and a lightweight API endpoint (`get_flatpak_card_meta`) to load developer/maintainer names and verification badges inline on grid/list view cards without triggering Flathub rate limits. Tests passed: 440.
- **Flathub aesthetic polish (2026-06-03).** The detail modal's badges and the permissions popup now closely match the official Flathub aesthetic. (1) **OARS age-rating & Form Factor**: `flathub.py` extracts `content_rating_details` and `type` from the v2 AppStream payload; these surface as simple pill badges ("15+ Age Rating", "Desktop Form Factor"). (2) **Dynamic sizes**: Download and installed sizes are dynamically extracted from the `get_info` RPC callback and prepended to the badges grid. (3) **Circular colored icons**: The Safety, License, and Publisher tiles use Flathub's signature colored circular backgrounds for their Material icons. (4) **Rich permission popup**: The permissions popup extracts up to 3 high-severity permissions into colored circles on the Safety badge itself, and the full popup list now includes a color-graded icon for every permission row. Tests passed: 440.
- **Context-aware empty/no-results state (2026-06-03).** Searching with no hits was hard to tell
  from loading. `renderPackages` now sets the `#empty-state` message by context: a search → "No
  results for “<query>”" + guidance; empty Updates → "Everything is up to date"; empty Installed →
  filter hint; else the generic message. (Loading is the skeleton grid via `getSkeletonGridHTML` in
  `fetchPackages` — verified still wired + styled, incl. `@keyframes shimmer`; skeletons show on
  uncached loads/searches, while the session `packageCache` makes repeat loads instant by design.)
- **AUR detail view: update-available + icon fix (2026-06-03).** Two issues a GUI check surfaced on
  an installed-but-behind AUR package (antigravity 2.0.6 vs 2.0.11): (1) **no update shown** —
  search results don't run the update check, so the card/modal showed "Uninstall" not "Update";
  (2) the **icon went blank** in the detail modal. Fixes: `get_aur_maintainer` → **`get_aur_meta`**,
  now also returns `latest_version` + `update_available` (computed with `vercmp` on installed vs AUR
  version). The detail modal shows an "↑ Update available (vX)" badge and **swaps the footer button
  to Update** when the on-demand check finds a newer version; and it now resolves the installed-app
  icon via `get_pkg_icon` (the same lazy path the cards use) instead of leaving a blank placeholder.
  Tests: +3 (8 total for `get_aur_meta`). Suite 440. *Caveat:* vercmp is version-string based, so a
  `-git`/VCS package with a static version string may not show the badge (the Updates page still
  catches it); fine for the common versioned case.
- **AUR maintainer info in the detail view (2026-06-03).** Follow-up to the maintainer advisory: it
  was build-time-only (banner in the update review modal) and thus undiscoverable. `openDetailModal`
  now shows, for AUR packages, a **👤 current-maintainer badge** (via new `AtlasApi.get_aur_maintainer`,
  one best-effort RPC) — fixing the "Unknown Publisher" gap (e.g. antigravity → AlphaLynx) — plus a
  clickable **⚠ Maintainer changed** badge (→ explainer popup) when a cached baseline differs, and an
  **⚠ Orphaned** badge when the package lost its maintainer. Tests: +5. Note: antigravity still won't
  show "changed" (no baseline cached at its install) — only the current maintainer.
- **AUR "maintainer changed hands" advisory (2026-06-03).** On an AUR *update*, `_audit_pkgbuild`
  compares the maintainer cached at install time (`context.maintainer`, baseline) against the current
  AUR maintainer (one best-effort `aur_client.get_info` RPC); if they differ (incl. now-orphaned →
  `new=None`) it adds `review['maintainer_change'] = {old, new}` and the review modal shows a warn
  banner ("Maintainer changed since you installed: X → Y") even when the PKGBUILD is clean and
  unchanged. Advisory only, gated on `aur_check_pkgbuild`. **Limitation:** packages installed before
  maintainer-caching have no baseline (e.g. an old `antigravity` showing "Unknown Publisher") so the
  first update can't compare — it re-caches and catches a *subsequent* change. Surfaces the
  supply-chain signal bauh only exposes accidentally (its duplicate-row display). Tests: +5. Plan:
  [plans/2026-06-03-aur-maintainer-change.md](plans/2026-06-03-aur-maintainer-change.md).
- **Fix: AUR index was gzip garbage → AUR-dep resolution broken (2026-06-03).** `packages.gz` is
  served as `application/gzip` with **no** `Content-Encoding`, so `requests` never decompressed it;
  `download_names`/`worker.update_index` split the raw gzip bytes (`res.text`) on `\n`, producing a
  ~5.9k-line *binary* index instead of the ~113.5k real names. Any AUR package whose deps weren't in
  repos failed dep resolution ("not found on the repositories nor AUR") — simple repo-dep AUR pkgs
  still worked, which hid it. New `aur.decode_index_response()` gunzips the body (falls back to plain
  text); used by both call sites. Tests: +3. Found while GUI-testing chroot builds with `protonup-qt`
  (deps `python-inputs`/`python-steam`). The on-disk index was also regenerated so installs work now.

- **AUR safety Layer 3 — clean-chroot builds, increments 1+2 (2026-06-03):** opt-in building of AUR
  packages in a devtools clean chroot (`makechrootpkg`), like paru/aurutils. **Engine** (`chroot.py`):
  `available()`/`missing_tools()` + argv builders (`create_root_cmd`/`update_root_cmd`/`build_cmd`,
  incl. `-U <user>` and `-I` injection). **Wiring** (`controller._build_in_chroot`): create-if-absent
  / update-else / build, swapped into `_build` behind `aur_build_chroot` (off) with a **host-build
  fallback** (devtools missing or chroot setup fails → never blocks an install). Privilege model
  **verified from the devtools source** (devtools installed on this box to confirm): run the tools as
  root; pass `-U atlas-aur` in the root path (makechrootpkg forbids root makepkg), rely on `SUDO_USER`
  in the unprivileged path. Tests: +18 (`test_chroot.py` 13, `test_chroot_build.py` 5); suite 419.
  **✓ Verified live (2026-06-03):** built `yay-bin` in a fresh chroot end-to-end — products landed in
  the package dir owned by the build user (pacman install works unchanged), deps resolved in-chroot.
  Fixed a real bug the live test surfaced: `mkarchroot`'s `readlink -f <dir>/root` needs the parent
  dir to exist, so `_build_in_chroot` now `mkdir -p`s the chroot dir first. **Settings toggle done**
  (2026-06-03): "Build AUR packages in a clean chroot" in the AUR-safety section, disabled with an
  "install devtools" hint when unavailable, honest help text. **`-I` dep-chain injection done**
  (2026-06-03): a per-transaction shared inject dir collects each built AUR package (deps build
  before dependents), propagated to dep contexts via `clone_base`; `_build_in_chroot` feeds them to
  `makechrootpkg -I`. **Bug fixed in increment 3:** increment 2 used `context.root_user`, which
  `TransactionContext` lacks (only `self.context.root_user` exists) → would `AttributeError` on every
  real chroot build; Mocks + the raw-shell live test had masked it, so the Atlas `_build_in_chroot`
  path had never actually run. Tests: +3 (suite 422). **v1 VERIFIED LIVE through the GUI
  (2026-06-03):** installed `protonup-qt` with chroot on — its AUR deps `python-inputs`/`python-steam`
  built in the chroot and the working copy's pacman log shows both injected (`-I`) into the copy
  right before `protonup-qt` built; all three installed on the host. Layer 3 done. Plan:
  [plans/2026-06-02-sandboxed-aur-builds.md](plans/2026-06-02-sandboxed-aur-builds.md).
- **AUR PKGBUILD review — rich rendered modal (2026-06-03):** the advisory pre-build review (which
  already scanned + diffed) now *renders* properly instead of dumping a plain-text wall into the
  confirm modal. New `pkgbuild_audit.diff_lines()` returns a structured unified diff
  (`{kind: meta/hunk/add/del/ctx, text}`); `_audit_pkgbuild` builds a `{name, summary, diff,
  findings}` `review` payload threaded through `request_confirmation` → `prompt_confirmation` →
  `showConfirmModal`. JS `renderPkgbuildReview()` draws a colored +/- diff (monospace, scrollable),
  severity-flagged lines, and an advisory banner ("N lines worth a look — a hint, not a safety
  check"); the modal widens (`has-review`). The blocking decision flow (`submit_confirmation` +
  threading.Event) is untouched — only rendering changed. Tests: +4 (`diff_lines`); gate test
  updated to assert the structured `review` kwarg; full suite 401. **Needs a GUI eyeball.**
- **Flatpak Permissions page — increment 3: Bus + Environment, + tabs (2026-06-03):** two more
  tabs on the Permissions page. **Bus**: session + system D-Bus name grants — list (entries
  revoked to `=none` are dropped), add (name + talk/own policy), remove. **Environment**: env-var
  list/add/remove. Also **tabbed the whole detail panel** (Share / Socket / Device / Features /
  Filesystem / Bus / Environment) since the combined list had grown long; active tab persists
  across the re-renders that edits trigger. Backend: `parse_context` now also parses
  `[Session/System Bus Policy]` + `[Environment]`; `bus_state`/`bus_flag`, `env_state`/`env_flag`;
  `set_bus_permission`/`set_env_permission` → `AtlasApi.set_flatpak_bus`/`set_flatpak_env`. Verified
  removal semantics against the real override keyfile (`--no-talk-name` ⇒ `=none`; `--unset-env` ⇒
  empty value, filtered out). Tests: `test_permissions.py` now 28 (+10); full suite 398. Live
  round-trip verified on Pinta. **Persist deferred** — `flatpak override` has no negative flag for
  persist, so clean removal needs keyfile editing (separate, riskier; the apps probed used none).
  **Needs a GUI eyeball.** Plan: [plans/2026-06-03-flatpak-permissions-page.md](plans/2026-06-03-flatpak-permissions-page.md).
- **Flatpak Permissions page — Flatseal-grade, increment 2: Filesystem (2026-06-03):** the
  Permissions page now has a **Filesystem** section — predefined dir toggles (host / host-os /
  host-etc / home + the `xdg-*` dirs), each with a per-row access **mode** (read/write, read-only,
  create), plus **custom-path add/remove**. Backend: `parse_context` keeps `filesystems_raw`
  (mode-bearing tokens) alongside the stripped set; `filesystem_state()` splits grants into
  presets vs custom; `filesystem_flag(name, enabled, mode)` → `--filesystem=X[:mode]` /
  `--nofilesystem=X`; `set_filesystem_permission` / `AtlasApi.set_flatpak_filesystem` glue.
  **Bug fixed along the way:** `flatpak.show_permissions` built `... <app> --None` when the
  installation arg was unset (the webview path always passes it unset), so it returned nothing —
  the grouped page *and* the in-modal editor were silently empty for installed apps. Now it
  appends branch/installation only when present. Tests: `test_permissions.py` now 24 (+6 for
  filesystem). Live-verified against Flatseal & Discord. Remaining: (3) Bus/Env/Persist dynamic
  lists. **Needs a GUI eyeball** (filesystem toggles + mode selects + add-path).
- **Dedicated Flatpak Permissions page — Flatseal-grade, increment 1 (2026-06-03):** a new
  **Permissions** sidebar page, **master/detail**: installed-Flatpak list (reuses `get_installed`,
  filtered to flatpak) → the selected app's permissions grouped (Share / Socket / Device / Features),
  each row = label + `flag=value` sub-label + an **iOS-style switch**, with per-app **Reset to
  defaults**. Refactored `permissions.py` to a generic scheme: `_CATEGORIES` + `GROUPS` +
  `grouped_toggles()`; `parse_context` now also reads `features`/`persistent`; `override_flag` is
  generic over `"<category>:<value>"` keys (`--allow/--disallow` for features, etc.). The in-modal
  quick editor was refactored onto the same scheme (kept — "keep both" per the UX call). New
  `FlatpakManager.get_grouped_permissions` + `AtlasApi.get_flatpak_grouped_permissions`; set/reset
  reuse the existing override path. Tests: `test_permissions.py` (18). Live-verified grouped output
  (Discord). Remaining increments (BACKLOG/plan): (2) Filesystem add/remove + ro/rw, (3) Bus/Env/Persist
  dynamic lists. Plan: [plans/2026-06-03-flatpak-permissions-page.md](plans/2026-06-03-flatpak-permissions-page.md).
  **Needs a GUI eyeball** (page layout, switches, toggling).
- **Flatpak transparency — metadata badges (theme increment 1, 2026-06-03):** the detail modal now
  shows Flathub badges for Flatpaks: **Open Source / Proprietary** (from `is_free_license` — Flathub
  pre-classifies, no SPDX parsing), **✓ Verified / ⚠ Unverified** (from the appstream
  `metadata['flathub::verification::*']`, already fetched — no extra call), and **downloads/month**
  (one `/api/v2/stats/<id>` call). `flathub.metadata_badges` + `installs_last_month` →
  `FlatpakManager.get_flathub_metadata` → `AtlasApi.get_flatpak_meta` (empty for non-Flatpak) →
  `#detail-badges` row in `openDetailModal` + `.meta-badge` styles. Best-effort/graceful. Live-verified
  (GIMP: FOSS/verified/67k; Spotify: proprietary/unverified/135k). Tests: `test_flathub.py` (+5),
  `test_api.py::FlatpakMetaTest` (2). **Increments 2+3 — permissions list + safety tier (2026-06-03):**
  the Flathub **`/api/v2/summary/<id>`** endpoint exposes the full structured permission set
  (sockets/filesystems/devices/shared/session-bus) for **any** app (installed or not), so we show
  what Flathub's "potentially unsafe" modal shows — no `flatpak info` needed. New pure module
  `atlas/gems/flatpak/permissions.py`: `describe(perms, is_free)` → human-readable risk-rated items
  (`{title, detail, level: safe|warn|danger}`, GNOME-Software-style), `safety()` → advisory tier
  (`unsafe`→"Potentially unsafe" / `moderate` / `safe`). `flathub.permissions()` fetches; folded into
  `get_flathub_metadata` (one extra summary call). Detail modal: a **safety badge** in the badges row
  + a **permissions list**, both clearly labeled *advisory, not a guarantee*. Live-verified vs
  Flathub (Dropbox → unsafe: home/+tmp/X11 danger, audio/network/non-portal/proprietary warn). Tests:
  `test_permissions.py` (11). **Click-to-popup UX (2026-06-03):** the permissions list moved into a
  click-triggered popup — the **safety badge** (now `… ⓘ`) opens the color-coded permission
  breakdown, and the **license badge** opens a FOSS-vs-proprietary explanation + the SPDX license.
  Generic `#info-popup` modal (z-index 400, above the detail modal) + `showInfoPopup()`; frontend-only.
  (Verified/unverified badge is clickable too, explaining Flathub verification — e.g. why Spotify is
  "unverified": community-packaged, not vendor-published.) **Increment 4 — Flatseal-style permission
  editing (2026-06-03, theme complete):** "⚙ Manage permissions" on installed Flatpaks opens a toggle
  editor (network, X11, Wayland, audio, all-devices, home, host). State read via `flatpak info
  --show-permissions` (`permissions.parse_context`/`editable_toggles`); each toggle applies via
  `flatpak override --user` (**no root**, `override_flag` maps key→flag); reset via `--reset`. Backend:
  `flatpak.{show_permissions,set_override,reset_overrides}` → `FlatpakManager.{get_permission_toggles,
  set_permission,reset_permissions}` → `AtlasApi.{get,set,reset}_flatpak_override(s)`. Toggles revert on
  failure, effective next launch. Live-verified parsing (Discord). Tests: `test_permissions.py` (now 15).
  **The Flatpak transparency & control theme is now complete** (metadata badges → permissions+safety →
  click-popups → editing). **Polish (2026-06-03):** each toggle now shows an explanatory sub-line +
  hover tooltip (`EDITABLE` entries carry `detail`); the "Manage permissions" button got proper
  spacing/alignment. A **dedicated Flatseal-style Permissions page** (sidebar) is roadmapped in
  BACKLOG (reuses the same backend). **Needs a GUI eyeball** (toggling writes the override file).
  Plan: [plans/2026-06-03-flatpak-transparency.md](plans/2026-06-03-flatpak-transparency.md).
  **Needs a GUI eyeball** (open a Flatpak's detail → badges + permissions).
- **Fix: installed AUR-only packages mislabeled as official-repo ("Arch") (2026-06-03):** a
  foreign installed package (repro: `atlas-pm-git`) showed a bogus two-source "Arch ● AUR" card.
  Trace: `read_installed` buckets a `not_signed` package that's missing from the (stale) cached AUR
  index into the *repo* path; `_fill_repo_pkgs` then sets `repository` from `pacman.map_repositories`
  (`pacman -Si`), which finds it in **no** sync repo → `None` → `get_type()='arch_repo'` ("Arch").
  `search()` then treats `None` as non-AUR and fails to de-dupe the AUR search hit → two-source card.
  Fix (`controller._fill_repo_pkgs`): a package pacman can't place in any real repo is **foreign**
  (AUR/community/local), not official-repo — label it **`'aur'`** instead of `None`. Surgical: genuine
  repo packages always get a real repo name from `-Si`, so they're untouched; no code relies on
  `repository is None`. **Index-freshness follow-up (2026-06-03):** the "Removed from AUR" category
  was flagged purely from the *stale cached index*, false-flagging just-published packages. Now
  `read_installed` RPC-verifies the index misses (`_confirm_removed_from_aur` → one batched
  `aur_client.get_info`) and only flags packages the **live RPC confirms are gone**; RPC
  failure/offline flags nothing (uncertain, not "all removed"). `_fill_repo_pkgs` takes the
  confirmed-removed set instead of doing the index check. Tests:
  `tests/gems/arch/test_repo_classification.py` (8: classification + RPC verification).
  **Needs a GUI eyeball** (search "atlas" → single AUR card, no false "Removed from AUR").
- **Better package icons (2026-06-03):** the grid was almost all letter-avatars (search results
  carry no icon for any source; icons were only fetched on the detail view). Three fixes:
  (1) **Flatpak icons in search** — `_serialize_pkg` derives the predictable Flathub CDN icon URL
  from the `app_id` (`dl.flathub.org/repo/appstream/x86_64/icons/128x128/<id>.png`, verified) when a
  Flatpak has no icon; the existing lazy-loader probes it and silently falls back to the avatar on
  404 / non-Flathub remotes. (2) **Multi-source best-icon** — `bestIconUrl(group)` makes a card use
  any source's icon (prefers data: then http), so e.g. **Steam** (Arch installed + Flatpak) borrows
  the Flatpak icon instead of showing a letter. (3) **Polished letter avatar** — gradient sheen +
  rounded tile + translucent glyph (was a flat square). Non-installed AUR/repo packages still have
  no icon source anywhere → avatar (inherent). Tests: `test_api.py::FlatpakIconFallbackTest` (3).
  **Installed-app icons (layer 4, 2026-06-03):** installed packages with no icon now resolve one
  from the system — `AtlasApi.get_pkg_icon(pkg_id)` parses the package's `.desktop` `Icon=`
  (`pacman -Ql`), falls back to an icon named after the package, finds the file in hicolor/pixmaps
  (plain FS search — no `Gtk.IconTheme`, for thread-safety), and base64-embeds it. Lazy + cached:
  the frontend stamps `data-pkgicon` on installed icon-less cards and the IntersectionObserver
  fetches + probes before swapping. Live-verified: steam→PNG, firefox→SVG. **Limits (graceful, →
  avatar):** SVG/PNG only (XPM can't render in WebKitGTK); only hicolor+pixmaps searched, so
  theme-specific icons (KDE/breeze, e.g. konsole) aren't found. Tests:
  `test_api.py::InstalledIconResolveTest` (5). Plan:
  [plans/2026-06-03-installed-app-icons.md](plans/2026-06-03-installed-app-icons.md). **Needs a GUI
  eyeball.**
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
- Documentation set at the time: ARCHITECTURE, ROADMAP, DEVELOPMENT, native-module API
  notes; cross-agent onboarding (AGENTS.md / CLAUDE.md / GEMINI.md) + this baton.
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

- **`refresh_mirrors` is an inert Manjaro leftover — intentionally left (2026-06-03).** The gem's
  `ArchManager.refresh_mirrors` / `pacman.refresh_mirrors` / `RefreshMirrors` worker use Manjaro's
  `pacman-mirrors -g`. On Arch/CachyOS this **never runs**: the custom action isn't surfaced in the
  webview at all, and the startup worker is double-gated off (`refresh_mirrors_startup` defaults off
  **and** `is_mirrors_available()` = `which pacman-mirrors`, absent on Arch). It's **superseded** by
  the Arch-correct `regenerate_mirrorlist` (reflector/rate-mirrors, in the `.pacnew` notice +
  Settings → Mirrors). **Decision (2026-06-03): leave it.** Full removal would refactor the startup
  DB-sync flow (`RefreshMirrors` feeds `SyncDatabases.should_sync(mirrors_refreshed, …)`) + the
  custom-action registry + `refresh_mirrors_startup` + i18n — a sensitive change for **zero runtime
  gain** (it's already inert). Not a bug; don't "fix" it. If ever removed, it's pure dead-code hygiene.
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

- **2026-06-17** — **Deferred remote signed audit rules-packs indefinitely (designed, not built).** The
  signing scheme is fully designed (plans/2026-06-17-audit-rules-pack-signing.md) but deliberately not
  implemented: a remote rule feed is a permanent supply-chain surface to own (crypto dep, key rotation/
  revocation, signing tooling + CI) and the value is marginal for an *advisory* scanner since Atlas
  ships as a fast-updating `-git` AUR package — new bundled rules already reach users on a normal
  update. The shipped local fail-closed loader (step 1) covers the real need. Revisit only if Atlas
  moves to a slow-release channel; if so, PyNaCl behind a `verify_pack()` seam. Reflects the maintainer's
  priority (solo dev, side project) to avoid standing maintenance burden.
- **2026-06-17** — **Dropped PKGBUILD-audit structural rule #3 (source-host ≠ url-host) on measured
  evidence.** Before building it, measured its fire rate on a random live AUR sample (via the new
  `atlas-cli audit-scan` / `parse_metadata`): on the 49/70 sampled packages declaring both a `url=` and
  a remote `source=()`, **45%** had no source host matching the url host (31% even at registrable-domain
  level), and every example was legitimate (homepage vs source repo, `*.github.io`→`github.com`, npm
  registry, vendor CDN, moved hosts). ~1-in-3 fire rate with ~all false positives = the alert-fatigue
  failure mode the maintenance plan explicitly warns against ("more rules ≠ safer"). No code shipped;
  recorded so it isn't rebuilt. This is also the first real payoff of the audit-scan tool: measure
  before adding a rule. See plans/2026-06-17-audit-structural-checks.md ("Step 3 — DROPPED").
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
