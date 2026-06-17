# Audit corpus re-scan tool (rule-health CLI)

**Date:** 2026-06-17
**Status:** ✅ Shipped 2026-06-17 (`atlas-cli audit-scan`; pure core + CLI wiring; suite 664).
Verified live: a 6-package sample flagged `weak_checksum`/`skip_checksum` as FP drift and read all
security rules 0× (as expected). Implements step (c) of
[2026-06-16-audit-rule-maintenance.md](2026-06-16-audit-rule-maintenance.md).

## Why

The ruleset will rot in two directions as it grows: a rule drifts into **false positives** (starts
firing on ordinary packages → alert fatigue), or a rule silently **stops matching anything** (a regex
bug, or a campaign that's over). The regression corpus (step b) guards *known* samples; this tool
gives the **review queue against live data**: sample N current AUR PKGBUILDs, scan them, and report
each rule's fire rate so a human can eyeball precision drift.

## Command

```
atlas-cli audit-scan [-n N] [--fp-threshold F] [-f text|json]
```
Samples N random AUR PKGBUILDs (default 200), scans each, and prints per-rule fire rates plus two
flagged buckets:
- **FP drift** — rules firing on ≥ `F` of the sample (default 0.5). High fire-rate on *random* (mostly
  benign) packages means the rule is broad/benign-common — review its precision.
- **Never fired** — rules that matched nothing in the sample. *Interpret with the rule's kind:* a
  malicious-pattern rule (reverse shell, exfil) firing 0× on random benign packages is **expected and
  healthy**, not stale — so the report shows `kind` alongside, and the real signal here is an
  *evergreen/structural* rule that never matches (possible regex bug).

## Design

**Pure core in `atlas/gems/arch/audit_rescan.py`** (unit-tested, no network):
- `aggregate_fire_counts(samples)` — `samples` = iterable of `(name, text)`; returns `(counts, total)`
  where `counts[rule]` = how many PKGBUILDs had ≥1 finding of that rule (deduped per file), `total` =
  files actually scanned (empty/None text skipped).
- `build_report(counts, total, fp_threshold)` — per-rule `{rule, count, pct, kind}` sorted by pct desc,
  plus `fp_drift` and `never_fired` buckets. Rule universe = `all_rule_ids()` **minus the
  `.SRCINFO` divergence rule** (it can't fire in a single-file `scan()`; the tool is PKGBUILD-only).
- `format_report_text(report)` — the human-readable table.

**Thin orchestration** `collect_samples(names, fetch_pkgbuild, sample, rng)` — shuffles names, takes the
first N, yields `(name, fetch_pkgbuild(name))`; a fetch returning None (404 / split-package whose
PKGBUILD lives under a different base / network blip) is yielded as `(name, None)` and skipped by the
aggregator. `fetch_pkgbuild` and `rng` are injected so this is testable with fakes.

**CLI wiring:** `cli_args.py` adds the `audit-scan` subparser; `app.py` routes it; `CLIManager`
gets an `audit_rescan(sample, fp_threshold, output_format)` that locates the arch manager (the one
exposing `aur_client` + `fetch_aur_file`), pulls names via `aur_client.download_names()`, and fetches
each PKGBUILD via `fetch_aur_file(name, 'PKGBUILD')`.

### Honesty / caveats (surfaced in the output header)
- Fetches by **package name as base** — split-package members whose base differs just 404 and are
  skipped (fine for a *sample*; not a census).
- Random benign sample → most security rules *should* read 0×. The tool flags **precision** drift
  reliably; "never fired" is advisory and kind-aware.
- PKGBUILD-only: the `.SRCINFO` divergence rule is out of scope here.

### Tests
`tests/gems/arch/test_audit_rescan.py` (pure, no network): `aggregate_fire_counts` (dedupe per file,
skips empty, counts total), `build_report` (pct math, fp_drift threshold incl. boundary, never_fired,
divergence rule excluded from the universe, kind attached), `collect_samples` (sample cap, shuffle via
injected rng, None passthrough), and `format_report_text` (renders buckets / empty sample).

## Non-goals
- No persistence/trend-over-time (just a point-in-time snapshot); no auto-tuning of rules.
- No `.SRCINFO` fetching (keeps it one request per sample).
- Not a census — a *sample*; not meant to be exhaustive or perfectly base-accurate.
