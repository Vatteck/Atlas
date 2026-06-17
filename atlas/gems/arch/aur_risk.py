"""Composite AUR trust score — a single advisory number aggregating signals Atlas already
collects (votes, popularity, package age, orphan status, maintainer-change) so the user doesn't
have to mentally combine several separate warnings.

Like `pkgbuild_audit`, this is a heuristic, **not** a safety verdict: a high score does not mean
a package is safe, only that it has the AUR-reputation signals trusted packages usually have.
"""
import time
from typing import Optional

TRUSTED = 'trusted'
CAUTION = 'caution'
RISK = 'risk'

_TRUSTED_MIN = 70
_CAUTION_MIN = 35

_WEIGHTS = {
    'votes': 0.30,
    'age': 0.25,
    'not_orphaned': 0.20,
    'maintainer_stable': 0.15,
    'popularity': 0.10,
}

_VOTES_CEILING = 500
_AGE_CEILING_YEARS = 2.0
_POPULARITY_CEILING = 2.0
_SECONDS_PER_YEAR = 365.25 * 24 * 3600


def _tier_for(score: float) -> str:
    if score >= _TRUSTED_MIN:
        return TRUSTED
    if score >= _CAUTION_MIN:
        return CAUTION
    return RISK


def calculate_aur_risk_score(pkg, maintainer_changed: bool, info: Optional[dict] = None) -> dict:
    """Composite reputation score for an AUR package.

    :param pkg: an `ArchPackage` (fallback source for `votes`, `popularity`, `first_submitted`,
                `maintainer`; all optional, missing data scores 0 for that factor).
    :param maintainer_changed: whether the AUR maintainer differs from the cached baseline.
    :param info: the AUR RPC `info` dict, when available. **Preferred** over the pkg attributes —
                 the pkg object in the detail/preview flow often lacks the AUR stats (votes etc.),
                 which would zero out those factors and produce a misleadingly low score.
    :return: {'score': int 0-100, 'tier', 'factors': {...}, 'breakdown': [{key,label,value,points,max}]}
    """
    if info:
        votes = info.get('NumVotes') or 0
        popularity = info.get('Popularity') or 0.0
        first_submitted = info.get('FirstSubmitted')
        maintainer = info.get('Maintainer')      # null here means genuinely orphaned
    else:
        votes = getattr(pkg, 'votes', None) or 0
        popularity = getattr(pkg, 'popularity', None) or 0.0
        first_submitted = getattr(pkg, 'first_submitted', None)
        maintainer = getattr(pkg, 'maintainer', None)

    votes_score = min(votes / _VOTES_CEILING, 1) * 100

    if first_submitted:
        age_years = max(time.time() - first_submitted, 0) / _SECONDS_PER_YEAR
        age_score = min(age_years / _AGE_CEILING_YEARS, 1) * 100
    else:
        age_years = 0.0
        age_score = 0.0

    not_orphaned_score = 100.0 if maintainer is not None else 0.0
    maintainer_stable_score = 0.0 if maintainer_changed else 100.0
    popularity_score = min(popularity / _POPULARITY_CEILING, 1) * 100

    factors = {
        'votes': votes_score,
        'age': age_score,
        'not_orphaned': not_orphaned_score,
        'maintainer_stable': maintainer_stable_score,
        'popularity': popularity_score,
    }
    score = sum(factors[name] * weight for name, weight in _WEIGHTS.items())
    score = round(max(0.0, min(100.0, score)))

    # Human-readable contribution of each signal, so the UI can explain the number.
    def _pts(name):
        return round(factors[name] * _WEIGHTS[name])

    def _max(name):
        return round(_WEIGHTS[name] * 100)

    breakdown = [
        {'key': 'votes', 'label': 'Community votes', 'value': f'{int(votes)}',
         'points': _pts('votes'), 'max': _max('votes')},
        {'key': 'age', 'label': 'Package age',
         'value': (f'{age_years:.1f} yr' if first_submitted else 'unknown'),
         'points': _pts('age'), 'max': _max('age')},
        {'key': 'not_orphaned', 'label': 'Maintainer',
         'value': ('present' if maintainer is not None else 'orphaned'),
         'points': _pts('not_orphaned'), 'max': _max('not_orphaned')},
        {'key': 'maintainer_stable', 'label': 'Maintainer stability',
         'value': ('changed recently' if maintainer_changed else 'stable'),
         'points': _pts('maintainer_stable'), 'max': _max('maintainer_stable')},
        {'key': 'popularity', 'label': 'Popularity',
         'value': f'{float(popularity):.2f}',
         'points': _pts('popularity'), 'max': _max('popularity')},
    ]

    return {'score': score, 'tier': _tier_for(score), 'factors': factors, 'breakdown': breakdown}
