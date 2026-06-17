# "Why is this installed?" — finish the attribution

**Date:** 2026-06-17 (drafted for a future session)
**Status:** Planning. BACKLOG item "Why is this installed?". **Most of it already shipped** — read
"What already exists" before writing code (verify, don't assume).

## What already exists (grounded — don't rebuild)

The core of this BACKLOG item landed with the dependency-summary work (2026-06-05); it just was never
ticked off the menu. Confirmed in the tree today:

- **Backend** `AtlasApi.get_dependency_summary` (`atlas/view/webview/api.py:1714`) already returns, for
  an *installed* package: `install_reason` (`'explicit'`/`'dependency'`, via
  `pacman.get_install_reason`), `required_by` (`pacman.map_required_by`), and a computed
  `orphan = install_reason == 'dependency' and not required_by`. Fails open per field.
- **Frontend** `buildDependencySummaryHTML` (`atlas/view/webview/main.js:1475`) already renders a
  **"Why is this installed?"** line:
  - explicit → "✓ You installed this explicitly."
  - dependency → "Installed as a dependency of other packages."
  - orphan → "⚠ Installed as a dependency, but nothing requires it now — an orphan you can likely
    remove."
  …plus a **"Required by"** chip group. (Reverse-deps were the other half of the BACKLOG line — done.)

So **explicit/dependency/orphan + required-by is shipped.** The only thing missing vs the BACKLOG
phrasing is *attribution*: "dependency **of what**?"

## The actual remaining delta

### (1) Name the explicit root(s) — the one real gap
Today a pulled-in dependency just says "a dependency of other packages." The power-user answer is
**"which package *you chose* dragged this in?"** `required_by` shows *direct* reverse-deps, but those
may themselves be dependencies — the satisfying answer walks up to the **explicitly-installed**
package(s).

- **Backend:** add the explicit roots to the installed/dependency branch of `get_dependency_summary`
  (or a small sibling helper). Algorithm, pure-pacman (no `pactree`/`pacman-contrib` dependency — keep
  the footprint low): BFS *upward* over `map_required_by` starting from the package, collecting any
  node that is explicitly installed (`pacman -Qeq` set), stopping a branch at the first explicit root.
  **Bound it** (visited-set, depth/▢node cap, e.g. ≤200 visited) and **fail open** to `[]` — this is
  advisory sugar, never a blocker. Return `installed_because: [explicit pkg names]`.
- **Frontend:** when `install_reason === 'dependency'` and `installed_because` is non-empty, render
  "Installed as a dependency of **X**, **Y**." (cap the list, "+N more"); fall back to the current
  generic line when the walk is empty/inconclusive. Orphan line unchanged.

### (2) Placement (small judgement call — decide when building)
The reason line currently lives *inside* the Dependencies accordion. The north-star intent ("know
what's happening") may want a one-line **mirror on the Overview** ("Installed: explicitly / as a
dependency of X · orphan"). Recommendation: a compact Overview line that reuses the same data, leaving
the detailed groups in Dependencies. Don't duplicate logic — one builder, two call sites, or a tiny
shared helper. Skip if it feels redundant on a GUI eyeball.

### (3) GUI eyeball
The existing reason line has never been explicitly eyeballed in isolation — verify it (and the new
attribution) on a real install with a known orphan + a known dependency.

## Tests
- Backend: `installed_because` walk — a dependency with one explicit root, multiple roots (capped),
  an orphan → `[]`, an explicit package → `[]` (n/a), the bound/visited-set terminates on a cycle,
  fail-open on a pacman error. (Mock `map_required_by` + the explicit set.)
- Frontend: `buildDependencySummaryHTML` — dependency-with-roots renders the names + "+N more";
  empty roots falls back to the generic line; explicit/orphan unchanged. (Node-VM contract test.)

## Non-goals
- No `pactree`/`expac`/`pacman-contrib` dependency — pure `pacman -Q*` only (low maintenance).
- No full reverse-dependency *tree* UI (the Dependencies accordion already drills down); just the
  explicit-root *names*.
- No new orphan-removal affordance — detail-page uninstall already exists; the orphan line is advisory.
- Flatpak/AUR-not-installed unchanged (no local install reason to read).

## Effort / risk
Small. One bounded pure-pacman backend helper + a frontend string change (+ optional Overline line).
Low risk (fail-open, advisory), low maintenance (local only, no infra). The "build it from scratch"
framing was wrong — this is a finish-and-polish, ~half a session.
