# IOC Database — Implementation Plan

> **Date:** 2026-07-16
> **Task:** Task 1 of AUR security heuristics plan (2026-06-21)
> **Agent:** Hermes (deepseek-v4-pro)

## What

Add an IOC (Indicators of Compromise) database to the PKGBUILD audit pipeline.
The database contains known-malicious AUR package names, npm/bun packages,
file artifacts, C2 domains, and attack accounts from the June 2026 Atomic Arch
AUR supply-chain campaign and subsequent discoveries.

## Design

### IOC Database (`atlas/gems/arch/data/malware_ioc.json`)

Schema:
```json
{
  "version": 1,
  "updated": "2026-07-16",
  "description": "...",
  "source": "...",
  "entries": {
    "aur_packages": [...],
    "npm_packages": [...],
    "bun_packages": [...],
    "file_artifacts": [...],
    "c2_domains": [...],
    "attack_accounts": [...]
  }
}
```

### Scanner integration (`atlas/gems/arch/pkgbuild_audit.py`)

- `_ioc_data`: Module-level variable, lazy-loaded via `_load_ioc_data()`.
- `_load_ioc_data(path=None) -> dict`: Loads from the bundled data file.
  Falls back to empty entries dict on any error.
- `_check_ioc(text, ioc_data) -> List[Dict]`: Scans each line of text against
  all IOC entries, returning findings with rule_id `known_ioc` and severity WARN.
- Wired into `scan()` after the structural checks (line 667+).
- IOC check only runs if `_ioc_data` is populated.

### Rule metadata

- Rule ID: `known_ioc`
- Severity: WARN
- Kind: CAMPAIGN
- Added: 2026-07
- Source: "Atomic Arch (June 2026) AUR supply-chain campaign — community IOC data (lenucksi/aur-malware-check, ks-aur-scanner)"

## Test plan

Create `tests/gems/arch/test_pkgbuild_audit_ioc.py`:

1. Known-bad AUR package names are flagged
2. Normal packages are not flagged
3. npm/bun package names in install commands are caught
4. File artifacts in PKGBUILDs are caught
5. Attack account names in maintainer/source fields are caught
6. Non-malicious package names don't fire
7. IOC data is lazy-loaded (doesn't load at import time)

## Verification

```bash
venv/bin/python -m pytest tests/gems/arch/test_pkgbuild_audit_ioc.py -v
venv/bin/python -m pytest tests/gems/arch/ -q
```
