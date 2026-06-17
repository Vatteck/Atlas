# PKGBUILD audit: structural / semantic checks

**Date:** 2026-06-17
**Status:** ✅ Step 1 shipped 2026-06-17 (network-in-`package()` + unchecksummed remote source; suite
638 + JS 55). Steps 3 (host-mismatch, may drop) and 4 (`.SRCINFO` divergence, needs plumbing) remain.
Parent: [2026-06-16-audit-rule-maintenance.md](2026-06-16-audit-rule-maintenance.md) (discovery #4).

## Why

The 33 existing rules are **line-by-line regex** — trivially evaded and prone to alert fatigue.
Discovery #4 in the maintenance plan flagged the higher-leverage move: **structural / semantic
checks** that look at the *whole file* and the *relationships between fields*. These are harder to
evade (you can't reword your way out of "there is a network call inside `package()`") and lower
false-positive (they encode real PKGBUILD semantics, not a surface pattern). Same guardrails:
offline, pattern/structure-based, advisory-only, no model/network/IOC feeds.

## What's available (grounded)

- `pkgbuild_audit.scan(text)` runs per-line and returns `{line_no, line, rule, severity, why}`.
  `api.get_pkgbuild` feeds it the **whole PKGBUILD text** (and each `.install`) — so a whole-file
  pass has everything it needs for steps 1–2 with **no new network plumbing**.
- `pkgbuild.parse_metadata(text)` already extracts `sources` (deduped URL list) and `checksums`
  (flattened `{algo, value, skip}`) — useful, but it **does not preserve per-index source↔checksum
  alignment**, so the unchecksummed-source check needs its own small ordered parser.
- `.SRCINFO` is fetched by the AUR client (`get_src_info`) but is **not currently passed to the
  scanner** — so the `.SRCINFO`↔PKGBUILD divergence check needs extra plumbing → deferred to step 3.

## The checks

| # | Check | Severity | Signal | FP risk | Step |
|---|-------|----------|--------|---------|------|
| 1 | **network in `package()`** | WARN | `package()` should only install built files; a curl/wget/pipe-to-shell/`/dev/tcp` there fetches+runs code at install-build time | low | **1** |
| 2 | **unchecksummed remote source** | WARN | a remote **http(s)** non-VCS `source=()` whose checksum is `SKIP`/absent in every `*sums` array → maintainer can swap the tarball with zero integrity check | low–med | **1** |
| 3 | source-host ≠ url-host | INFO | download host differs from project homepage | **high** (github-releases vs homepage, mirrors) | later / maybe drop |
| 4 | `.SRCINFO` ↔ PKGBUILD divergence | WARN | published metadata disagrees with the build script | low, but needs `.SRCINFO` plumbing | 3 |

Steps 3–4 are deliberately *not* in this change: #3 is high-FP (needs evidence it earns its noise),
#4 needs the `.SRCINFO` passed through `get_pkgbuild`.

## Step 1 design (this change)

Add a **whole-file pass** alongside the per-line `_RULES`: a small list of structural analyzers
`(rule_id, severity, why, analyzer)` where `analyzer(text) -> List[finding]` (each carrying the most
relevant `line_no` for the viewer, or the field's line). `scan()` runs the per-line rules first
(unchanged), then appends the structural findings, then re-sorts by `line_no`. Structural rules also
get `_RULE_META` provenance (`kind=evergreen`, `added=2026-06-17`, `source='structural checks'`) and
go in the regression corpus.

- **`network_in_package`**: locate the `package()` body (brace-matched span via a small
  `_function_span` helper that handles `name()`, `name ()`, `function name`), then reuse the existing
  network/pipe matchers on those lines only. Fires once per offending line inside `package()`.
- **`unchecksummed_remote_source`**: a dedicated ordered parser pairs the plain `source=()` array with
  the plain `*sums=()` arrays by index (arch-suffixed `_x86_64` arrays ignored in v1 — conservative,
  fewer FPs). Flag a source entry when it's a **remote http(s)** URL, **not** a VCS proto
  (`git+`/`svn+`/`hg+`/`bzr+`), and **every** present checksum at its index is `SKIP` (or missing).
  Local-file sources and VCS sources are *expected* to SKIP → never flagged (that stays the generic
  `skip_checksum` INFO).

### Tests
- Positive + FP-safe unit tests per check (network in `build()` is fine; a `git+` SKIP is fine; an
  https tarball with a real sha256 is fine; a local-file SKIP is fine).
- New corpus files: a benign split-package/VCS PKGBUILD (must stay WARN-free) and a malicious one with
  a `curl … | sh` inside `package()` + an https tarball SKIP (must WARN).
- Metadata guard counts updated.

## Non-goals (this change)
- Checks #3 and #4 (host-mismatch, `.SRCINFO` divergence).
- Arch-suffixed source/sums alignment (`source_x86_64`) — v1 analyzes the default arrays only.
- Any UI surfacing of "structural" vs "regex" finding kind (the metadata is there for later).
