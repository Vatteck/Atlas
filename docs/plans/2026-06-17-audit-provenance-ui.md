# Surface rule provenance in the PKGBUILD viewer

**Date:** 2026-06-17
**Status:** ✅ Shipped 2026-06-17 (backend `meta` on every finding + `findingProvenanceHTML` in the
viewer; suite 649 + JS 55). **Needs a GUI eyeball.** Follow-up to
[2026-06-16-audit-rule-maintenance.md](2026-06-16-audit-rule-maintenance.md) (step a left this as a
non-goal) and [2026-06-17-audit-structural-checks.md](2026-06-17-audit-structural-checks.md).

## Why

We recorded `kind`/`added`/`source` for each rule (`rule_metadata()`), but it's invisible to users.
Surfacing it makes each advisory finding **transparent and accountable**: the reader can see the
stable rule id (to look up / report), whether it's a durable technique (*evergreen*) or one tied to a
specific incident (*campaign* — e.g. the Atomic Arch attack), and where the rule came from. This
directly supports the "advisory, read-it-yourself" framing — no black-box badge.

## Design

**Backend (small):** attach provenance to every finding. `scan()` and `scan_divergence()` already
have the rule id at construction time; add `'meta': rule_metadata(rule_id)` (→ `{kind, added,
source}`) to each finding dict. Cheap, uniform, and every consumer (viewer list, `.install` tab) gets
it. No change to existing keys, so existing tests/assertions hold.

**Frontend:** in `buildPkgbuildFindingsHTML`, render a compact provenance row under each finding:
- the **rule id** as a small mono chip (always), so the heuristic is identifiable;
- a **"campaign"** pill *only* for campaign rules (the meaningful distinction; evergreen is the
  unremarkable baseline);
- a `title` tooltip with the full line — e.g. `Evergreen rule · added 2026-06-17 · source: structural/
  semantic checks` — so detail is available on hover without cluttering the list.

A pure helper `findingProvenanceHTML(f)` builds this from `f.meta` + `f.rule`; it returns `''` when
neither is present (backward-compatible with findings that predate provenance / JS fixtures).

### Tests
- JS: `findingProvenanceHTML` (campaign pill, rule chip, tooltip text, empty when no meta) +
  `buildPkgbuildFindingsHTML` still links to the line and now includes the rule id.
- Python: a finding from `scan()` and from `scan_divergence()` carries a `meta` dict with the expected
  `kind`/`source`.

## Non-goals
- No filtering/sorting of findings by kind, no "hide campaign rules" control (could come later).
- No provenance on the diff badges (they already show the rule name) or the transaction-preview
  review list — viewer findings only, for now.
