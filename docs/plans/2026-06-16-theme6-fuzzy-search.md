# Theme 6: Fuzzy package search

**Date:** 2026-06-16
**Status:** Parts 1 (re-rank) and 2 (local filter + fuzzy fallback) ✅ shipped 2026-06-16. Dedicated
plan for competitive-research Theme 6 (Pacsea's fuzzy matching).
Parent: [2026-06-16-competitive-research-improvements.md](2026-06-16-competitive-research-improvements.md).

## Goal

Make package search **typo- and partial-tolerant** and surface the most relevant hit first, instead
of today's exact-substring behaviour where `widget` won't find `wodget` and ordering is backend-only.

## What exists today (grounded)

- A good fuzzy scorer already exists for the command palette: **`fuzzyScore(query, text)`** (subsequence
  match; rewards contiguous runs + word-start boundaries; `-1` = no match), used by `filterCommands`.
- Package search is **backend-driven**: a non-empty query calls `pyApiCall('search', query, 'all')`
  (its own matching, incl. the AUR RPC). The client then runs `renderFiltered()`, which applies the
  **source-type filter only** — no text re-ranking.
- Installed / Updates are **finite local lists** (`get_installed`, `getUpdatesCached`) but a query in
  those views *also* goes through the backend `search`, not a local filter.

## Design (client-side only — no backend change)

Two scoped, low-risk improvements, both reusing `fuzzyScore`:

### 1. Re-rank backend results by relevance — ✅ shipped 2026-06-16
- After `search` returns, **stable-sort** the results by `fuzzyScore(query, pkg.name)` (tie-break:
  keep backend order). Exact/substring hits naturally score highest, so this only *reorders* — it
  never drops a backend result. Put the obvious match on top.
- **Shipped:** pure `rerankByFuzzy(results, query)` (reuses `fuzzyScore` over `name`/`display_name`,
  stable on ties, never drops, passthrough for empty query / <2 results / bad input). Applied to the
  `pyApiCall('search', …)` result before `writeToCache`, so cached hits keep the ranked order. Test:
  `main_js_contracts::testRerankByFuzzy`. JS **53**. **Needs a GUI eyeball** (search a partial/typo'd
  name → the obvious package is at the top).

### 2. Fuzzy fallback when there are zero exact hits (local lists) — ✅ shipped 2026-06-16
- For the finite local lists (Installed, Updates), add a **client-side fuzzy filter**: when the query
  has **no exact substring match** in the current list, fall back to `fuzzyScore`-ranked entries above
  a **threshold** (so `wodget` still finds `widget`). Exact matches always win and are shown first;
  fuzzy results are clearly secondary.
- **Shipped:** pure `filterLocalPackages(list, query)` (exact name/description substring → relevance
  order; else, query ≥3 chars → fuzzy *name* matches with `fuzzyScore ≥ 8`, ranked; empty query →
  full list). `fetchPackages` now routes a query in Installed/Updates (`PACKAGE_LIST_VIEWS`) through it
  against the cached full list (`localListFor`, reused from the no-query load — no extra backend call),
  instead of the global `search`. Test: `main_js_contracts::testFilterLocalPackages`. JS **54**.
- **Behaviour change (intended):** searching from the **Installed**/**Updates** view now filters
  *that view's* packages rather than running a global cross-source search. (To find/install a *new*
  package, use Browse/Dashboard search.) **Needs a GUI eyeball** + a user thumbs-up on this change.
- Constants `LOCAL_FUZZY_MIN_SCORE = 8`, `LOCAL_FUZZY_MIN_QUERY_LEN = 3` are the tunable knobs.

### Threshold discipline (the main risk)
Loose fuzzy feels random. Guardrails:
- Only show fuzzy results when exact matches are absent (or below a small count), never *instead* of
  exact matches.
- Require a minimum score (tuned constant) and a minimum query length (e.g. ≥3 chars) before fuzzy
  kicks in — short queries match too much.
- Keep `fuzzyScore` as the single shared implementation (no second scorer to drift).

## Tests (contract, Node VM — pure)
- A small pure helper `rerankByFuzzy(results, query)` (stable, never drops items, best-name-match
  first) — unit-test ordering + stability + empty-query passthrough.
- A `fuzzyFallback(list, query, {minScore, minLen})` helper — returns `[]` when an exact match exists
  or the query is too short; returns threshold-ranked matches otherwise. Unit-test the typo case and
  the "don't fire on exact/short" cases.

## Non-goals
- No server-side change (the AUR RPC keeps its own matching).
- No fuzzy on the global cross-source `search` *query* itself (backend owns that) — only client-side
  **re-ranking** of what it returns + local-list fallback.
- No new scorer — reuse `fuzzyScore`.

## Effort / risk
Small (client-only, reuses `fuzzyScore`), low risk if the threshold discipline above is followed.
Recommended to ship #1 (re-rank) first — it's pure upside — and gate #2 (fallback) behind the
threshold tuning.
