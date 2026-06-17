import unittest

from atlas.gems.arch import audit_rescan as rs
from atlas.gems.arch import pkgbuild_audit as audit


# PKGBUILD snippets with known rule hits.
_PIPE = "build() {\n  curl -sL https://x/y | sh\n}\n"            # pipe_to_shell + network_cmd
_SUDO = "package() {\n  sudo cp x /etc/y\n}\n"                    # sudo
_CLEAN = "pkgname=demo\npkgver=1\nbuild() { make; }\n"           # nothing


class AggregateFireCountsTest(unittest.TestCase):
    def test_counts_per_file_and_total(self):
        counts, total = rs.aggregate_fire_counts(
            [('a', _PIPE), ('b', _SUDO), ('c', _CLEAN)])
        self.assertEqual(total, 3)
        self.assertEqual(counts.get('sudo'), 1)
        self.assertEqual(counts.get('pipe_to_shell'), 1)

    def test_dedupes_within_a_file(self):
        # two sudo lines in one file → still counts the file once for that rule
        text = "package() {\n  sudo a\n  sudo b\n}\n"
        counts, total = rs.aggregate_fire_counts([('x', text)])
        self.assertEqual(total, 1)
        self.assertEqual(counts.get('sudo'), 1)

    def test_skips_empty_and_none(self):
        counts, total = rs.aggregate_fire_counts([('a', None), ('b', ''), ('c', _SUDO)])
        self.assertEqual(total, 1)
        self.assertEqual(counts.get('sudo'), 1)


class BuildReportTest(unittest.TestCase):
    def test_pct_and_buckets(self):
        # sudo fires on 2/4, pipe on 1/4.
        counts = {'sudo': 2, 'pipe_to_shell': 1}
        report = rs.build_report(counts, total=4, fp_threshold=0.5)
        self.assertEqual(report['total'], 4)
        by_rule = {r['rule']: r for r in report['rules']}
        self.assertAlmostEqual(by_rule['sudo']['pct'], 0.5)
        self.assertAlmostEqual(by_rule['pipe_to_shell']['pct'], 0.25)
        # fp_drift includes sudo (>= 0.5 boundary) but not pipe
        drift = {r['rule'] for r in report['fp_drift']}
        self.assertIn('sudo', drift)
        self.assertNotIn('pipe_to_shell', drift)

    def test_never_fired_lists_zero_count_rules_with_kind(self):
        report = rs.build_report({'sudo': 1}, total=2)
        never = {r['rule']: r for r in report['never_fired']}
        self.assertIn('eval', never)              # an evergreen rule that didn't fire
        self.assertNotIn('sudo', never)
        self.assertIn(never['eval']['kind'], (audit.EVERGREEN, audit.CAMPAIGN))

    def test_divergence_rule_excluded_from_universe(self):
        report = rs.build_report({}, total=1)
        rules = {r['rule'] for r in report['rules']}
        self.assertNotIn(audit.SRCINFO_DIVERGENCE_RULE, rules)
        # but the single-file structural rules are present
        self.assertIn('network_in_package', rules)

    def test_zero_total_is_safe(self):
        report = rs.build_report({}, total=0)
        self.assertEqual(report['total'], 0)
        self.assertEqual(report['fp_drift'], [])           # nothing flagged when nothing scanned
        self.assertTrue(all(r['pct'] == 0.0 for r in report['rules']))

    def test_rules_sorted_by_fire_rate_desc(self):
        report = rs.build_report({'sudo': 3, 'eval': 1}, total=3)
        pcts = [r['pct'] for r in report['rules']]
        self.assertEqual(pcts, sorted(pcts, reverse=True))


class CollectSamplesTest(unittest.TestCase):
    class _Rng:
        def shuffle(self, seq):  # deterministic: leave order as-is
            pass

    def test_caps_to_sample_and_fetches_each(self):
        fetched = []
        out = list(rs.collect_samples(
            ['a', 'b', 'c', 'd'], lambda n: fetched.append(n) or f'PKGBUILD-{n}',
            sample=2, rng=self._Rng()))
        self.assertEqual([n for n, _ in out], ['a', 'b'])
        self.assertEqual(out[0], ('a', 'PKGBUILD-a'))
        self.assertEqual(fetched, ['a', 'b'])

    def test_none_fetch_passes_through(self):
        out = list(rs.collect_samples(['a'], lambda n: None, sample=5, rng=self._Rng()))
        self.assertEqual(out, [('a', None)])

    def test_empty_names(self):
        self.assertEqual([], list(rs.collect_samples([], lambda n: 'x', sample=5, rng=self._Rng())))

    def test_uses_injected_rng_to_shuffle(self):
        class Rev:
            def shuffle(self, seq):
                seq.reverse()
        out = list(rs.collect_samples(['a', 'b', 'c'], lambda n: n, sample=2, rng=Rev()))
        self.assertEqual([n for n, _ in out], ['c', 'b'])


class FormatReportTest(unittest.TestCase):
    def test_text_renders_buckets(self):
        report = rs.build_report({'sudo': 2}, total=2)
        text = rs.format_report_text(report)
        self.assertIn('2 PKGBUILD(s) scanned', text)
        self.assertIn('sudo', text)
        self.assertIn('FP drift', text)

    def test_text_handles_empty_sample(self):
        text = rs.format_report_text(rs.build_report({}, total=0))
        self.assertIn('No PKGBUILDs were scanned', text)

    def test_json_round_trips(self):
        import json
        report = rs.build_report({'sudo': 1}, total=2)
        self.assertEqual(json.loads(rs.format_report_json(report))['total'], 2)


if __name__ == '__main__':
    unittest.main()
