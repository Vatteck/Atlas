"""Rule-health re-scan: sample live AUR PKGBUILDs and report each audit rule's fire rate.

The regression corpus (tests/gems/arch/audit_corpus) guards *known* samples; this is the review
queue against *live* data — it surfaces precision drift (a rule firing on a large fraction of
ordinary packages) and rules that match nothing. See docs/plans/2026-06-17-audit-corpus-rescan.md.

Network I/O is kept out of the pure functions here (`fetch_pkgbuild`/`rng` are injected) so the
logic is unit-testable offline; the CLI wires the real AUR client in.
"""
import json
import random
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from atlas.gems.arch import pkgbuild_audit as audit

# The divergence rule needs a .SRCINFO (cross-file); this tool scans PKGBUILDs only, so it can never
# fire here. Exclude it from the universe so it isn't mis-reported as a "never fired / stale" rule.
_SINGLE_FILE_RULES = sorted(audit.all_rule_ids() - {audit.SRCINFO_DIVERGENCE_RULE})


def aggregate_fire_counts(samples: Iterable[Tuple[str, Optional[str]]]) -> Tuple[Dict[str, int], int]:
    """Count, across the sampled PKGBUILDs, how many had ≥1 finding of each rule.

    `samples` is an iterable of (name, text); empty/None text is skipped (a failed fetch). Returns
    (counts, total) where counts[rule] is the per-file hit count (deduped within a file) and total is
    the number of files actually scanned."""
    counts: Dict[str, int] = {}
    total = 0
    for _name, text in samples:
        if not text:
            continue
        total += 1
        for rule in {f['rule'] for f in audit.scan(text)}:
            counts[rule] = counts.get(rule, 0) + 1
    return counts, total


def build_report(counts: Dict[str, int], total: int, fp_threshold: float = 0.5) -> Dict:
    """Per-rule fire rates + two flagged buckets. Rule universe is every single-file rule (so a rule
    that matched nothing still appears with count 0). `pct` is 0 when nothing was scanned."""
    per_rule: List[Dict] = []
    for rule in _SINGLE_FILE_RULES:
        count = counts.get(rule, 0)
        pct = (count / total) if total else 0.0
        per_rule.append({'rule': rule, 'count': count, 'pct': pct,
                         'kind': audit.rule_metadata(rule)['kind']})
    per_rule.sort(key=lambda r: (-r['pct'], r['rule']))
    fp_drift = [r for r in per_rule if total and r['pct'] >= fp_threshold]
    never_fired = [r for r in per_rule if r['count'] == 0]
    return {'total': total, 'fp_threshold': fp_threshold, 'rules': per_rule,
            'fp_drift': fp_drift, 'never_fired': never_fired}


def collect_samples(names: List[str], fetch_pkgbuild: Callable[[str], Optional[str]],
                    sample: int, rng=random) -> Iterable[Tuple[str, Optional[str]]]:
    """Shuffle `names`, take the first `sample`, and yield (name, fetch_pkgbuild(name)). A fetch that
    returns None (404 / split-package base mismatch / network blip) is yielded through and skipped by
    the aggregator. `fetch_pkgbuild` and `rng` are injected for testability."""
    pool = list(names or [])
    rng.shuffle(pool)
    for name in pool[:max(0, sample)]:
        yield name, fetch_pkgbuild(name)


def format_report_text(report: Dict) -> str:
    """Human-readable rule-health report."""
    total = report['total']
    lines = []
    lines.append(f"Audit rule-health re-scan — {total} PKGBUILD(s) scanned")
    lines.append("(random AUR sample, PKGBUILD-only; fetched by name-as-base so split packages may be "
                 "skipped.")
    lines.append(" A security rule reading 0× on benign packages is expected — read 'never fired' "
                 "with the rule's kind.)")
    if not total:
        lines.append("\nNo PKGBUILDs were scanned (no names, or all fetches failed).")
        return '\n'.join(lines)

    thr = int(report['fp_threshold'] * 100)
    lines.append(f"\nFP drift — rules firing on ≥{thr}% of the sample (review precision):")
    if report['fp_drift']:
        for r in report['fp_drift']:
            lines.append(f"  {r['pct']*100:5.1f}%  {r['rule']:<28} [{r['kind']}]  ({r['count']}/{total})")
    else:
        lines.append("  (none)")

    lines.append("\nNever fired in this sample (expected for incident/malicious rules; check evergreen "
                 "ones for a broken matcher):")
    if report['never_fired']:
        for r in report['never_fired']:
            lines.append(f"         {r['rule']:<28} [{r['kind']}]")
    else:
        lines.append("  (none)")

    lines.append("\nAll rules by fire rate:")
    for r in report['rules']:
        lines.append(f"  {r['pct']*100:5.1f}%  {r['rule']:<28} [{r['kind']}]  ({r['count']}/{total})")
    return '\n'.join(lines)


def format_report_json(report: Dict) -> str:
    return json.dumps(report)
