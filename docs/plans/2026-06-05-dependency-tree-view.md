# Dependency tree view (2026-06-05)

**Backlog item:** "Dependency tree view — direct/optional/build deps + required-by + conflict/
replaces/provides, as an accordion tree (not node spaghetti)." (Power-user sugar)

## Why
The detail page's **Dependencies** section already shows Requires / Optional / Required-by counts as
expandable chip lists (the dependency-summary work). This completes the picture: the missing
relationship types (**build deps, conflicts, replaces, provides**) and makes the direct/build deps a
real **drill-down tree** — click a dependency to lazily reveal *its* dependencies, one cheap level at
a time. Honest, calm, and Arch-aware — no node-graph spaghetti.

## Scope (honest, fail-open)
Reuses the same cheap pacman/AUR signals as the dependency summary + transaction preview; **fails
open per field** (a failed probe → empty group). No new resolver.

## Increment 1 (this change)
### Backend — extend `AtlasApi.get_dependency_summary`
Additive fields (existing `direct`/`optional`/`required_by`/`install_reason`/`orphan`/`note` stay):
- `makedepends`, `checkdepends` — build-time deps. **AUR only** (binary repo packages don't carry
  them in `pacman -Si`); from AUR `get_info` `MakeDepends`/`CheckDepends`.
- `conflicts` — repo: `map_updates_data` `c`; AUR: `get_info` `Conflicts`.
- `replaces` — repo: `map_conflicts_with` `r`; AUR: `get_info` `Replaces`.
- `provides` — repo: `map_updates_data` `p`; AUR: `get_info` `Provides`.

### Backend — new `AtlasApi.get_subdeps(name)`
Cheap direct-requires for a single package **name** (for lazy tree expansion): repo via
`pacman.map_updates_data([name])` `d`; returns `{direct:[str]}`. Fails open → `{direct:[]}`
(AUR-only names / errors → leaf). Repo-resolved only (no per-node AUR RPC storms).

### Frontend
- `buildDependencySummaryHTML` renders the new groups as additional accordion blocks: **Build**
  (make+check), **Provides**, **Conflicts**, **Replaces** (each collapsible, count-badged), keeping
  Requires / Optional / Required-by + the install-reason banner + note.
- **Drill-down tree:** the **Requires** and **Build** group bodies become lists of expandable
  **dependency nodes** (pure `buildDepNodesHTML(names)`) instead of flat chips. Expanding a node
  lazily fetches `get_subdeps(name)` and renders its direct requires as the same expandable nodes —
  drill arbitrarily deep, one click per level (recursion bounded by the user). Optional / Provides /
  Conflicts / Replaces / Required-by stay flat chips (relationships, not a tree).
- Lazy + stale-guarded by the existing `renderDependencySummary` (re-render path unchanged); a
  delegated click handler on the deps body loads each node's children once.

### Tests
- `test_api.py::DependencySummaryTest` — new groups (repo + AUR) + fail-open; `get_subdeps` happy +
  fail-open.
- `main_js_contracts` — `buildDepNodesHTML` (node markup + `data-dep`), `buildDependencySummaryHTML`
  renders the new groups + requires-as-nodes (existing assertions kept).

## Non-goals
- No eager full-tree resolution (expensive; N pacman calls). One level per click, lazy.
- No reverse-dependency *tree* (required-by stays a flat list — upward spaghetti).
- No version-constraint solving; we show declared relationships, not a SAT result.
