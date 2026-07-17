# AUR Audit Detection Rules — Task 2 Implementation Plan

**Date:** 2026-07-16  
**Parent plan:** [2026-06-21-aur-security-heuristics.md](2026-06-21-aur-security-heuristics.md)  
**Status:** Implementing

## Objective

Add 4 new detection rules to `atlas/gems/arch/pkgbuild_audit.py` based on aur-audit's detection categories (MIT-licensed, safe to adapt). These are additive — no existing rules are modified.

## New Rules

| Rule ID | aur-audit Ref | Pattern | Severity |
|---------|--------------|---------|----------|
| `pipe_eval_remote` | EXEC-01 | `sh <(curl)` / `bash <(wget -qO-)` — the Atomic Arch delivery mechanism | WARN |
| `systemd_unit_install` | PERS-01 | Writing `.service`/`.timer` to absolute systemd paths during install hooks | WARN |
| `shell_rc_write` | ENV-01 | Writing to shell init files via `>`, `cat >`, `tee -a`, etc. (extends `shell_function_inject`) | WARN |
| `host_tamper` | WRITE-01 | Writes to absolute system paths outside `$pkgdir`/`$srcdir` | WARN |

## Implementation Steps

1. **Add rules to `_RULES` list** in `pkgbuild_audit.py` (before `_RULE_META`)
2. **Add metadata entries** to `_RULE_META` (EVERGREEN, source: aur-audit)
3. **Add test cases** to `test_pkgbuild_audit.py`:
   - Each rule gets a positive test (should fire) and negative test (similar-but-safe should not fire)
   - Run `pytest tests/gems/arch/test_pkgbuild_audit.py -v` to verify
4. **Run full test suite**: `venv/bin/python -m pytest tests/gems/arch/ -q`
5. **Verify corpus**: benign samples must not fire new WARN rules

## Notes

- Rules are additive only — the existing scan pipeline is untouched
- Each rule carries a source attribution comment mentioning aur-audit
- The existing `shell_function_inject` catches `>>` appends; `shell_rc_write` catches `>`, `cat >`, `tee -a`, and other write patterns
- The existing `pipe_to_shell` catches `<(curl ...)` generally; `pipe_eval_remote` specifically targets `bash <(curl ...)` (shell invocation + process substitution together)
