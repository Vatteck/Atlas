# PKGBUILD audit: discovering new patterns + keeping the ruleset fresh

**Date:** 2026-06-16
**Status:** ✅ Steps (a)+(b) shipped 2026-06-17 (rule provenance side map + regression corpus; suite
630 + JS 55). Strategy + remaining steps (c)(d) and discovery #4 are follow-ups. Parent context:
[2026-06-16-competitive-research-improvements.md](2026-06-16-competitive-research-improvements.md) (Theme 1).

## Framing (the real constraint)

`pkgbuild_audit.py` is 31 pure-regex rules, offline, advisory-only. Regex heuristics are **trivially
evadable**, so the failure mode that matters isn't "missed a rule" — it's **alert fatigue**: low-signal
rules train users to ignore the badge. "More rules ≠ safer" (already in the Theme-1 plan). Stay
pattern-based + offline-by-default + precision-conscious; the guardrails from the competitive-research
plan still hold (no external scanners, no IOC/hash feeds, no LLM auditing).

## Discovery — finding more negative patterns

1. **Mine real incidents** (reactive, high precision): arch-security list, AUR deletion/flag notices,
   `r/archlinux` malware threads, supply-chain write-ups. Each documented attack → one targeted rule
   (how the Atomic Arch rules were born).
2. **Borrow rule *categories*, not code**: ks-aur-scanner (mined ~17/115), Semgrep registry, shell
   YARA, MITRE ATT&CK techniques (T1059/T1547/T1071). Map technique → regex.
3. **Corpus-driven** (scalable): the AUR is public (we already fetch `packages.gz` + cgit). Build a
   local corpus → (a) **rarity/anomaly** flagging (long-tail constructs) to catch *novel* patterns no
   one wrote a rule for; (b) **FP tuning** against known-good packages.
4. **Structural/semantic checks beat more regex** (hard to evade, low FP): network in `package()`,
   `source=` host ≠ `url=` host, unchecksummed binary `source=`, `.SRCINFO`↔`PKGBUILD` divergence.
5. **Community signal** (pipe already exists): AUR comments often shout "malware"; combine with the
   orphan/out-of-date/votes signals already in the reputation score.

## Freshness — keeping it updated

a. **Rules as data with provenance**: each rule gets `kind` (evergreen vs campaign), `added`, and a
   `source`. Lets us audit *why* a rule exists and **retire** dead-campaign rules. ← *step (a) below*
b. **CI regression corpus**: two fixture sets — known-malicious whole-file samples (**must** flag) and
   realistic known-good PKGBUILDs (**must not** raise a WARN; INFO advisories are allowed). Stops a
   tightening from silently breaking detection or a new rule from spiking FPs. ← *step (b) below*
c. **Periodic corpus re-scan tool** (`atlas-cli`/`/schedule`): sample N current AUR PKGBUILDs, report
   rules that now fire on *everything* (FP drift) and *nothing* (stale). The review queue.
d. **Optional signed rules-pack in `atlas-files`**: engine stays pure-Python/offline in `atlas/`; rule
   *data* ships as a versioned file in the runtime-data repo so a new rule lands without an app
   release. Must be signed/reviewed and **fail closed to the bundled rules** (a remote rule feed is
   itself a supply-chain surface).

## This change — steps (a) + (b)

### (a) Rule metadata + evergreen/campaign split
- Add `EVERGREEN`/`CAMPAIGN` constants and a `_RULE_META` map keyed by rule id (kind/added/source),
  plus a `rule_metadata(id)` accessor (defaults: evergreen, no source — the "pre-metadata baseline"
  for the original 14). **Design choice:** keep metadata in a side map rather than rewriting the 31
  rule tuples — this avoids editing the security-sensitive regex lines (transcription risk) for a
  pure-bookkeeping change. Co-locating into a `Rule` namedtuple is a fine future refactor.
- Honesty: only record `added`/`source` we actually know — the 17 ks-aur-scanner-derived rules
  (2026-06-16), the 2 Atomic Arch campaign rules (2026-06); the original 14 stay evergreen/None.
- Guard tests: every `_RULE_META` key is a real rule; every campaign rule has a source; counts add up.

### (b) Regression corpus
- `tests/gems/arch/audit_corpus/{benign,malicious}/*.pkgbuild` + a loader test:
  - **benign** realistic PKGBUILDs → **no WARN** findings (INFO allowed — e.g. a `-git` SKIP or a
    daemon's `systemctl enable`).
  - **malicious** whole-file samples (reverse shell, credential exfil, persistence) → **≥1 WARN**.
- Growing the corpus = drop a file in; CI runs it.

## Not in this change (follow-ups)
- Surfacing `source`/`kind` in the PKGBUILD viewer UI.
- The corpus re-scan tool (c) and the `atlas-files` rules-pack (d).
- Structural/semantic checks (discovery #4) — their own plan.
