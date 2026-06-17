# AUR reputation: correct the score + make it legible + fill badge space

**Date:** 2026-06-16
**Status:** ✅ shipped 2026-06-16 (needs a GUI eyeball). Suite 618 + JS 52 green.
**Trigger:** GUI eyeball — android-studio (a hugely popular AUR pkg) shows **15 · Risk**, and it's not
clear to the user how that number arises. Also the Overview badge grid has lots of blank space.

## Root cause (the score is wrong)

`calculate_aur_risk_score(pkg, ...)` reads `votes/popularity/first_submitted/maintainer` off the
**ArchPackage object**. In the detail/preview flow that object has those as `None` (they aren't
populated from local DB / search), so votes/age/popularity all score 0 — even though
`get_aur_meta` / `_preview_aur` *just fetched* the AUR RPC `info` that contains the real
`NumVotes`/`Popularity`/`FirstSubmitted`/`Maintainer`. android-studio's 15 is exactly
`maintainer_stable` (100 × 0.15) and nothing else — a pure artifact.

## Changes

### Backend — `aur_risk.py`
- `calculate_aur_risk_score(pkg, maintainer_changed, info=None)`: when `info` (the RPC dict) is
  given, derive the inputs from it (`NumVotes`/`Popularity`/`FirstSubmitted`/`Maintainer`) — these
  are the fresh, authoritative values; else fall back to the pkg attributes (back-compat).
- Add a **`breakdown`** list to the return: per factor `{key, label, value, points, max}` where
  `points` = factor_score × weight (rounded) and `max` = weight × 100, so the UI can show exactly
  how each signal contributed to the total.

### Backend — `api.py`
- `get_aur_meta`: pass `info=info`; also return raw `votes`, `popularity`, `out_of_date` for badges.
- `_preview_aur`: pass `info=info`.
- `get_update_risk_tiers`: keep the full per-name info dict and pass `info=` (batch path fixed too).

### Frontend — `main.js`
- **Legibility:** make the Reputation badge clickable (`data-popup="reputation"`) →
  `showInfoPopup('AUR reputation', reputationPopupHtml(risk))`. Pure `reputationPopupHtml` renders the
  score/tier, each breakdown row (`label … points/max`), and the "heuristic, not a safety check"
  disclaimer.
- **Blank space:** add **Votes** and **Popularity** badges (and an **Out of date** badge when
  flagged) from `get_aur_meta` data — these are the score's own inputs, so they fill the grid *and*
  reinforce the reputation number at a glance.

### Tests
- `test_aur_risk.py`: `info` overrides bare pkg (popular pkg → high score, not 15); `breakdown`
  present and points≈score.
- `test_api.py::AurMetaTest`: votes/popularity surfaced; risk computed from info.
- `main_js_contracts`: `reputationPopupHtml` renders rows + escapes; (badge wiring is GUI-eyeballed).

## Non-goals
- No new RPC calls (reuse the `info` already fetched).
- Don't change the weights/tiers — only *where the inputs come from* and *how it's explained*.
