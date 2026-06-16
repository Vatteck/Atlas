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


def calculate_aur_risk_score(pkg, maintainer_changed: bool) -> dict:
    """Composite reputation score for an AUR package.

    :param pkg: an `ArchPackage` (only `votes`, `popularity`, `first_submitted`, `maintainer`
                are read; all are optional and missing data scores 0 for that factor).
    :param maintainer_changed: whether the AUR maintainer differs from the cached baseline.
    :return: {'score': int 0-100, 'tier': 'trusted'|'caution'|'risk', 'factors': {...}}
    """
    votes = getattr(pkg, 'votes', None) or 0
    popularity = getattr(pkg, 'popularity', None) or 0.0
    first_submitted = getattr(pkg, 'first_submitted', None)
    maintainer = getattr(pkg, 'maintainer', None)

    votes_score = min(votes / _VOTES_CEILING, 1) * 100

    if first_submitted:
        age_years = max(time.time() - first_submitted, 0) / _SECONDS_PER_YEAR
        age_score = min(age_years / _AGE_CEILING_YEARS, 1) * 100
    else:
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

    return {'score': score, 'tier': _tier_for(score), 'factors': factors}
