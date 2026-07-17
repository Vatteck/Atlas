# Audit Rule-Health Dashboard — 2026-07-16

## Problem

`audit_rescan.py` exists but is CLI-only. Users can't see which audit rules
are firing too often (false positives) or never firing (broken regex or obsolete
pattern). The System Health page is the natural place for this — it already shows
pacman lock status, pacnew files, orphan packages, etc. Rule health is the missing
maintenance signal.

## Solution

Add a read-only audit rule-health check to the System Health page.

### API
- `start_audit_rescan(sample_size=100)` — starts a background scan (samples AUR
  package names from the index, fetches PKGBUILDs, runs the audit engine, builds
  a report). Returns immediately with cached result or "started" status.
- `get_audit_rescan_result()` — returns the last cached report or None.
  The report has `{total, rules:[{rule, count, pct, kind}], fp_drift, never_fired}`.

### Frontend
- New System Health check card: "PKGBUILD Audit Rules"
  - If never scanned: "Run a sample scan to check for noisy or stale rules"
  - If scanned: shows rule counts, highlights FP drift rules and never-fired rules
  - Action button: "Rescan" or "Run sample scan"

### Scope
- Read-only, advisory only — never blocks package operations
- Background threaded so the UI stays responsive
- Fails open — scan failures just show "Scan unavailable"

## Non-changes
- Not adding a scheduled cron rescan (manual trigger only for now)
- Not exposing the full per-rule table inline (that's a follow-up)
