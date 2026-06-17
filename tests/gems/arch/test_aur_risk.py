import time
import unittest
from types import SimpleNamespace

from atlas.gems.arch import aur_risk


def _pkg(votes=None, popularity=None, age_years=None, maintainer='someone'):
    first_submitted = None
    if age_years is not None:
        first_submitted = int(time.time() - age_years * aur_risk._SECONDS_PER_YEAR)
    return SimpleNamespace(votes=votes, popularity=popularity,
                            first_submitted=first_submitted, maintainer=maintainer)


class AurRiskScoreTest(unittest.TestCase):
    def test_well_established_package_is_trusted(self):
        pkg = _pkg(votes=500, popularity=2.0, age_years=3, maintainer='alice')
        result = aur_risk.calculate_aur_risk_score(pkg, maintainer_changed=False)
        self.assertEqual(result['score'], 100)
        self.assertEqual(result['tier'], aur_risk.TRUSTED)

    def test_moderate_package_is_caution(self):
        pkg = _pkg(votes=100, popularity=0.5, age_years=1, maintainer='alice')
        result = aur_risk.calculate_aur_risk_score(pkg, maintainer_changed=False)
        self.assertEqual(result['score'], 56)
        self.assertEqual(result['tier'], aur_risk.CAUTION)

    def test_new_orphaned_changed_package_is_risk(self):
        pkg = _pkg(votes=5, popularity=0.05, age_years=1 / 12, maintainer=None)
        result = aur_risk.calculate_aur_risk_score(pkg, maintainer_changed=True)
        self.assertLess(result['score'], aur_risk._CAUTION_MIN)
        self.assertEqual(result['tier'], aur_risk.RISK)

    def test_missing_fields_score_zero_for_that_factor_not_crash(self):
        pkg = SimpleNamespace(votes=None, popularity=None, first_submitted=None, maintainer=None)
        result = aur_risk.calculate_aur_risk_score(pkg, maintainer_changed=False)
        self.assertIsInstance(result['score'], int)
        self.assertIn(result['tier'], (aur_risk.TRUSTED, aur_risk.CAUTION, aur_risk.RISK))
        self.assertEqual(result['factors']['votes'], 0)
        self.assertEqual(result['factors']['age'], 0)
        self.assertEqual(result['factors']['not_orphaned'], 0)

    def test_maintainer_changed_drops_maintainer_stable_factor_to_zero(self):
        pkg = _pkg(votes=500, popularity=2.0, age_years=3, maintainer='alice')
        unchanged = aur_risk.calculate_aur_risk_score(pkg, maintainer_changed=False)
        changed = aur_risk.calculate_aur_risk_score(pkg, maintainer_changed=True)
        self.assertEqual(changed['factors']['maintainer_stable'], 0.0)
        self.assertEqual(unchanged['factors']['maintainer_stable'], 100.0)
        self.assertLess(changed['score'], unchanged['score'])

    def test_score_bounded_0_to_100(self):
        pkg = _pkg(votes=10000, popularity=50, age_years=50, maintainer='alice')
        result = aur_risk.calculate_aur_risk_score(pkg, maintainer_changed=False)
        self.assertLessEqual(result['score'], 100)
        self.assertGreaterEqual(result['score'], 0)

    def test_rpc_info_overrides_bare_pkg(self):
        # The detail-flow bug: a pkg object with no AUR stats would score ~15, but the fresh RPC
        # info has the real numbers and must win — a popular package scores high, not Risk.
        bare = SimpleNamespace(votes=None, popularity=None, first_submitted=None, maintainer=None)
        info = {'NumVotes': 500, 'Popularity': 2.0, 'Maintainer': 'alice',
                'FirstSubmitted': int(time.time() - 3 * aur_risk._SECONDS_PER_YEAR)}
        from_bare = aur_risk.calculate_aur_risk_score(bare, maintainer_changed=False)
        from_info = aur_risk.calculate_aur_risk_score(bare, maintainer_changed=False, info=info)
        self.assertLess(from_bare['score'], aur_risk._CAUTION_MIN)   # the misleading artifact
        self.assertEqual(from_info['score'], 100)                    # the real reputation
        self.assertEqual(from_info['tier'], aur_risk.TRUSTED)

    def test_rpc_info_null_maintainer_is_orphaned(self):
        info = {'NumVotes': 500, 'Popularity': 2.0, 'Maintainer': None,
                'FirstSubmitted': int(time.time() - 3 * aur_risk._SECONDS_PER_YEAR)}
        result = aur_risk.calculate_aur_risk_score(SimpleNamespace(), maintainer_changed=False, info=info)
        self.assertEqual(result['factors']['not_orphaned'], 0.0)

    def test_breakdown_explains_the_score(self):
        pkg = _pkg(votes=500, popularity=2.0, age_years=3, maintainer='alice')
        result = aur_risk.calculate_aur_risk_score(pkg, maintainer_changed=False)
        keys = [b['key'] for b in result['breakdown']]
        self.assertEqual(keys, ['votes', 'age', 'not_orphaned', 'maintainer_stable', 'popularity'])
        # each row carries a display value + points/max; points sum to the total (full marks here)
        self.assertTrue(all({'key', 'label', 'value', 'points', 'max'} <= set(b) for b in result['breakdown']))
        self.assertEqual(sum(b['points'] for b in result['breakdown']), result['score'])
        self.assertEqual(sum(b['max'] for b in result['breakdown']), 100)


if __name__ == '__main__':
    unittest.main()
