# AUR Reputation Scoring, Diff Security Annotation, Batch Update Risk Tiers

**Status: implemented 2026-06-16** — all three features below shipped in one session; see
`docs/STATUS.md` Done log for the summary and exact files touched.

## Context

Atlas 0.12.0 just shipped with 14 PKGBUILD audit rules (4 added today for Atomic Arch),
maintainer-change detection, a first-class PKGBUILD viewer with diff-since-last-build, and
opt-in clean-chroot builds. The security infrastructure exists; what's missing is a
**quantitative signal** that surfaces trust at a glance, and **annotated diffs** that highlight
which changed lines are the suspicious ones.

The AUR RPC data needed for reputation scoring is already fetched and stored on `ArchPackage`
— this is a pure computation on existing data, no new network calls.

---

## Recommended next features (ordered by impact/effort)

### 1. AUR Reputation Scoring — `atlas/gems/arch/aur_risk.py` (new)

**What it is**: A `calculate_aur_risk_score(pkg: ArchPackage, maintainer_changed: bool) -> dict`
function returning `{score: 0-100, tier: "trusted"|"caution"|"risk", factors: {…}}`.

**Why this matters**: Currently Atlas shows *separate signals* (orphaned, out-of-date,
maintainer-changed) as independent warnings. A single composite score gives users an
at-a-glance risk indicator without requiring them to mentally aggregate multiple warnings.

#### Scoring formula

Five weighted sub-scores, each normalised to [0, 100], weighted average → final score.

| Signal | Weight | Ceiling / notes |
|---|---|---|
| Votes | 0.30 | `min(votes / 500, 1) * 100` — 500 votes → full 30 pts |
| Package age | 0.25 | `min(age_years / 2.0, 1) * 100` — 2 yr → full 25 pts |
| Not orphaned | 0.20 | 100 if `pkg.maintainer` not None, else 0 |
| Maintainer stable | 0.15 | 100 if `not maintainer_changed`, else 0 |
| Popularity | 0.10 | `min(popularity / 2.0, 1) * 100` — AUR pop ≈ 0-5, cap at 2.0 |

**Calibration check**:
- Well-established (500 votes, 3yr old, same maintainer, pop 2.0) → **100 → "trusted"**
- New adopted orphan (5 votes, 1 month old, changed, pop 0.05) → **~4 → "risk"**
- Moderate (100 votes, 1yr, stable, pop 0.5) → **~56 → "caution"**

**Tiers**: ≥ 70 = trusted (green), 35–69 = caution (amber), < 35 = risk (red).

**Note on orphan detection**: `pkg.orphan` is already a property on `ArchPackage` (`model.py:289`):
`return self.maintainer is None`. Use it directly — no new field needed.

#### Integration points in `api.py`

**`_preview_aur()`** (lines 2058–2091): The `maintainer_changed` boolean is already
computed inline (line 2084). Extract it to a local variable, then call the scorer, add
`data['aur_risk'] = risk` alongside `data['warnings']`. Fail-open in a try/except.

**`get_aur_meta()`** (lines 1815–1850): `changed` is already computed (line 1834).
`maintainer_changed = changed is not None`. Call scorer, add `'risk': risk` to the return
dict on line 1846. Fail-open in a try/except.

#### Frontend changes

**Detail page** (`main.js:2756` — AUR branch of `get_aur_meta`): Add a reputation badge
to the `parts` array (same pattern as the existing "Update Available" and "Maintainer Changed"
`rich-badge-tile` entries). Only render if `info.risk && info.risk.score !== undefined`.
Badge color class: `trusted` → green, `caution` → amber, `risk` → red.

**Preview modal** (`main.js:~1006` — the `buildTxpHtml` / warnings renderer): Read
`data.aur_risk` from the preview response and render a score indicator above the warnings
list. The `warnings` list itself stays unchanged — the badge is a peer key.

---

### 2. Diff Security Annotation (follow-on, ~2–3 hours)

**What it is**: Extend `diff_lines()` in `pkgbuild_audit.py` with an `annotate=True`
parameter. When enabled, runs `scan(new_text)` once, builds a `{stripped_line: [findings]}`
lookup, and attaches `findings: [...]` to each `add` diff entry whose content matches.
Non-`add` lines and non-matching `add` lines carry `findings: []` (or the key is absent for
`annotate=False` — unchanged default, all existing tests pass).

**Matching logic**: `diff_line[1:].strip()` (strip leading `+`, then whitespace) compared
against `finding['line']` which `scan()` stores as `raw.strip()`. Exact string match.

**Call site**: `get_pkgbuild()` in `api.py` already calls `diff_lines(old_text, text)`.
Change to `diff_lines(old_text, text, annotate=True)`.

**Frontend**: In `renderPkgbuildReview()` (`main.js:872`), the diff tab already renders
`add`/`del`/`ctx` lines. When a line has `findings.length > 0`, render a small inline
warning badge (e.g., `⚠ npm_install_unknown`) to the right of the diff line.

---

### 3. Batch Update Security Tiers

**Important architectural finding**: the Update-All aggregate preview (`buildUpdateAllPreviewData`,
`main.js:1178`) is built **entirely client-side** from the already-loaded `currentPackages` list —
there is no per-package server round trip today (only two cheap aggregate calls:
`check_upgrade_news`, `get_pacnew_files`). This keeps Update-All fast even with many pending
updates. Naively computing a reputation score per AUR package would require fetching the *current*
AUR maintainer for each one (the serialized `maintainer` field on an installed package is the
**cached baseline**, not the live value — see `model.py:87` `__cached_attrs`), which is exactly
the signal needed for `maintainer_changed`. Doing this with N individual RPCs would slow down
Update-All proportionally to the AUR update count. The AUR RPC's `get_info()` already accepts a
batch of names in one call (`aur.py:90`, used by `gen_updates_data`), so the fix is a **single
batched call**, not N calls.

#### New backend method: `get_update_risk_tiers(pkg_ids: list) -> dict`

```python
def get_update_risk_tiers(self, pkg_ids: List[str]) -> dict:
    """One batched AUR RPC call to score every pending AUR update for the Update-All preview.
    Non-AUR packages are tier 'safe' by source type (official repo / Flatpak are not scored).
    Fails open: any RPC error → all AUR packages fall back to tier 'caution' (never silently
    'safe', never blocks)."""
    pkgs = [self._get_pkg(pid) for pid in pkg_ids]
    pkgs = [p for p in pkgs if p]
    aur_pkgs = [p for p in pkgs if (getattr(p, 'repository', None) or '') == 'aur']
    results = {}
    for p in pkgs:
        if (getattr(p, 'repository', None) or '') != 'aur':
            results[p.id] = {'tier': 'safe', 'score': None}  # official repo / Flatpak: not scored

    if aur_pkgs:
        arch_man = self._manager_by_gem('arch')
        aur_client = getattr(arch_man, 'aur_client', None)
        try:
            infos = aur_client.get_info([p.name for p in aur_pkgs]) if aur_client else []
            current_by_name = {i['Name']: i.get('Maintainer') for i in (infos or [])}
            for p in aur_pkgs:
                baseline = getattr(p, 'maintainer', None)
                current = current_by_name.get(p.name)
                changed = bool(baseline and current and current != baseline)
                risk = calculate_aur_risk_score(p, changed)
                results[p.id] = {'tier': risk['tier'], 'score': risk['score']}
        except Exception as e:
            self.logger.debug(f"get_update_risk_tiers: batch RPC failed: {e}")
            for p in aur_pkgs:
                results.setdefault(p.id, {'tier': 'caution', 'score': None})  # fail open, not 'safe'

    counts = {'safe': 0, 'caution': 0, 'risk': 0}
    for r in results.values():
        counts[r['tier'] if r['tier'] in counts else 'caution'] += 1
    return {'status': 'ok', 'data': {'tiers': results, 'counts': counts}}
```

Map score tiers to update-tier labels: `trusted` → `safe`, `caution` → `caution`, `risk` → `risk`.

#### Frontend changes

`updateAllBtn` handler (`main.js:3130`) already gathers `news`/`pacnew` signals before building
the preview. Add one more call: `const riskTiers = await pyApiCall('get_update_risk_tiers', updates.map(p => p.id));`
then pass `riskTiers.data` into `buildUpdateAllPreviewData(updates, {…, tiers: riskTiers.data})`.

Inside `buildUpdateAllPreviewData`, add a tier breakdown line to `notes` (or a small 3-segment bar):
`"42 safe to update · 5 worth a review · 1 high risk"`. If `counts.risk > 0`, add a `warn`-level
entry to `data.warnings` naming the high-risk packages so they're not buried in an aggregate count
— reuse the existing `warnings` rendering, don't invent a new UI primitive.

**Scope boundary**: this only **categorizes and surfaces** risk — it does not change what Update
All actually does (it still updates everything in one shot, consistent with Atlas's existing
behavior and its advisory-only philosophy). Per-package deselection from a batch update is a
larger, separate feature and is out of scope here.

#### Prerequisite fix: serialize `first_submitted`

`_serialize_pkg` (`api.py:579-586`) already serializes `votes`, `popularity`, `last_modified`,
`maintainer`, `out_of_date`, `package_base` — but **not** `first_submitted`, which the age
component of `calculate_aur_risk_score` needs. Since `get_update_risk_tiers` computes scores
server-side from `ArchPackage` objects (not from the serialized JS dicts), this is only required
if a future feature needs the score computed client-side. Not needed for #1–#3 as designed, since
all three call `calculate_aur_risk_score` server-side. No serializer change needed.

---

## Files to change

### New
- `atlas/gems/arch/aur_risk.py` — the scoring module (~50 lines of pure Python)
- `tests/gems/arch/test_aur_risk.py` — calibration tests for the three tier scenarios + None fields

### Modified
- `atlas/view/webview/api.py` — `_preview_aur()`, `get_aur_meta()` (< 15 lines each), plus new
  `get_update_risk_tiers()` method (~30 lines) exposed as a JS-callable API
- `atlas/gems/arch/pkgbuild_audit.py` — `diff_lines()` gains `annotate` param (~20 lines)
- `atlas/view/webview/main.js` — reputation badge in detail page + preview modal (~30 lines);
  `updateAllBtn` handler gains the `get_update_risk_tiers` call (~5 lines); `buildUpdateAllPreviewData`
  gains tier-breakdown notes + high-risk warning entries (~15 lines); `renderPkgbuildReview()` diff
  tab gains inline finding badges (~15 lines)
- `tests/gems/arch/test_pkgbuild_audit.py` — tests for annotated diff (~10 lines)

---

## What NOT to build yet

- **LLM scanning**: Needs explicit sign-off — sits in the non-goals grey zone ("AI
  recommendations are cringe"). Frame it as a security analysis tool if/when brought up.
- **Post-install eBPF monitoring**: `/sys/fs/bpf/` is unreadable without root; most of the
  interesting checks require privilege the GUI doesn't have.
- **Making chroot the default**: Requires sign-off per AGENTS.md §3; would frustrate users
  without devtools installed.

---

## Verification

```bash
# After implementing aur_risk.py:
python3 -m pytest tests/gems/arch/test_aur_risk.py -v

# After diff annotation:
python3 -m pytest tests/gems/arch/test_pkgbuild_audit.py -v

# Full suite:
python3 -m pytest -x -q

# Manual: open Atlas, navigate to an installed AUR package's detail page,
# confirm reputation badge appears in the detail metadata section.
# Navigate to an AUR package with a pending update, open the PKGBUILD viewer
# → Diff tab, confirm suspicious added lines show inline warning badges.
# Click Update All with multiple pending AUR updates queued: confirm the preview
# shows a tier breakdown line (safe/caution/risk counts) and that any 'risk' tier
# packages are named in the warnings list, with no added latency from N+1 RPCs
# (only one extra batched get_update_risk_tiers call, visible in --logs).
```
