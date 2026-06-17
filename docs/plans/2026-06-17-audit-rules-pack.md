# Audit rules-pack: external rule data (loader first, signing/remote gated)

**Date:** 2026-06-17
**Status:** ✅ Step 1 shipped 2026-06-17 (local, validated, fail-closed loader; suite 673). Verified
end-to-end: a local `audit_rules.json` is picked up by `scan()` and appears in `audit-scan`'s universe.
Steps 2–3
(signing, `atlas-files` remote distribution) are **explicitly gated on user sign-off** — a remote
rule feed is a supply-chain surface. Implements step (d) of
[2026-06-16-audit-rule-maintenance.md](2026-06-16-audit-rule-maintenance.md).

## Goal & the hard constraint

Let a new *regex* rule land **without an app release** by shipping rule *data* the engine loads,
while the engine itself stays pure-Python/offline. The catch: the bundled rules aren't all regex —
several use Python matcher functions (`_has_base64_literal`, `_unchecksummed_remote_source`, …) that
**cannot** be serialized safely. So a rules-pack can only carry **pattern (regex) rules**; structural
and helper-function checks stay in code. That's fine — the long tail of "one incident → one regex" is
exactly what benefits from out-of-band updates.

## Guardrails (non-negotiable)

1. **Additive only.** A pack *adds* rules; it never edits or removes a bundled rule. The 33 bundled
   rules are untouched (no transcription risk on the security-sensitive lines — the maintenance plan's
   recurring worry). A pack rule whose id collides with a bundled id is **rejected** (bundled wins).
2. **Fail closed to bundled.** Any problem — missing file, bad JSON, wrong shape, an invalid rule —
   degrades to *fewer* external rules, never to a broken scan. A malformed pack loads zero rules; the
   bundled set always works. Suppression-proof: a pack can't disable a bundled rule.
3. **Strict validation + ReDoS-awareness.** Every field is type/enum/length-checked and the pattern
   must compile; pattern length is capped. Scanned text is small (PKGBUILDs), bounding backtracking —
   but a *remote* pack (step 2) must use a timeout-capable engine, since untrusted regex can ReDoS.
4. **Local only in step 1.** Step 1 loads a *local* file (`$CONFIG/arch/audit_rules.json`) — same
   trust level as the user's own config; no network, so **no signing needed yet**. The moment the pack
   is sourced remotely (step 2), signing + signature-verify-or-ignore becomes mandatory.

## Step 1 (this change) — the loader

In `pkgbuild_audit.py`:
- **Format** (JSON): `{"version": 1, "rules": [{id, severity, why, pattern, flags?, kind?, added?,
  source?}, …]}`. `severity ∈ {warn,info}`; `flags ⊆ {i,m,s}`; `kind ∈ {evergreen,campaign}`
  (default evergreen); `id` matches `^[a-z][a-z0-9_]*$` and is not a bundled id.
- `load_rule_pack(obj) -> (rules, meta)` — pure validator. Returns `([], {})` on a bad top-level
  shape; **skips** individual invalid rules (logs nothing — advisory), keeps the valid ones; dedupes
  ids within the pack. Compiles each pattern to a `.search` matcher.
- `register_rule_pack(obj) -> int` / `reset_rule_packs()` — set/clear module-level `_EXTERNAL_RULES`
  + `_EXTERNAL_META`. `load_rule_pack_file(path, logger) -> int` reads+parses+registers, fails closed.
- Integration: `scan()` runs bundled per-line rules, then `_EXTERNAL_RULES` (same per-line, comment-
  skipping, try/except-guarded loop), attaching `rule_metadata(id)` (now also consulting
  `_EXTERNAL_META`). `all_rule_ids()` and `rule_metadata()` include external ids. Findings from a pack
  are indistinguishable in shape and carry provenance, so the viewer's rule-id chip + kind tooltip
  already surface them.
- **Activation:** `AtlasApi` loads `$CONFIG/arch/audit_rules.json` once at init (best-effort). No file
  → no change in behaviour. `audit-scan` picks up external rules automatically (shared `all_rule_ids`).

### Tests
`test_pkgbuild_audit.py` additions (pure, no I/O): valid pack loads + fires in `scan()` with meta;
bad shapes → `([], {})`; per-rule rejects (bad severity, uncompilable pattern, id collision with a
bundled rule, bad id charset, over-length); dedupe; `reset_rule_packs` isolation; `load_rule_pack_file`
fails closed on a missing/garbage file; `all_rule_ids`/`rule_metadata` include a registered pack rule.

## Steps 2–3 (NOT in this change — need sign-off)

- **Signing.** Bundle an Ed25519/minisign public key; sign the pack in `atlas-files`; verify on load
  and **ignore an unsigned/invalid pack** (fail closed). Without this, do not load a *remote* pack.
- **`atlas-files` distribution.** Ship `arch/audit_rules.json` (+ `.sig`) in the runtime-data repo,
  fetch into cache like `categories.txt`, fall back to bundled on any fetch/verify failure. Versioned.
- **ReDoS hardening** for untrusted patterns (timeout-capable matching).

## Non-goals
- No remote fetch, no signing, no `atlas-files` change in step 1.
- Packs can't define function/structural checks — regex rules only.
- No UI to author packs; it's a data file.
