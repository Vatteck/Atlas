"""Regression corpus for the PKGBUILD audit scanner.

Two fixture sets under `audit_corpus/` guard against the two ways the ruleset rots
(docs/plans/2026-06-16-audit-rule-maintenance.md, step b):

* `benign/`    — realistic, known-good PKGBUILDs. These **must not raise a WARN**. INFO advisories
                 are allowed (a `-git` SKIP, a daemon's service install) — they're low-stakes hints.
                 A WARN here is a false positive that erodes trust in the badge.
* `malicious/` — whole-file samples of real attack shapes (reverse shell, credential exfil,
                 persistence/obfuscation). Each **must raise at least one WARN**. A miss here means
                 a tightening silently broke detection.

Grow the corpus by dropping a `.pkgbuild` file into the right folder — this test discovers them.
"""
import os
import unittest

from atlas.gems.arch import pkgbuild_audit as audit

_CORPUS_DIR = os.path.join(os.path.dirname(__file__), 'audit_corpus')


def _samples(kind):
    folder = os.path.join(_CORPUS_DIR, kind)
    out = []
    for name in sorted(os.listdir(folder)):
        if name.endswith('.pkgbuild'):
            with open(os.path.join(folder, name), encoding='utf-8') as fh:
                out.append((name, fh.read()))
    return out


def _warns(findings):
    return [f for f in findings if f['severity'] == audit.WARN]


class BenignCorpusTest(unittest.TestCase):
    def test_benign_samples_raise_no_warn(self):
        samples = _samples('benign')
        self.assertTrue(samples, 'benign corpus is empty')
        for name, text in samples:
            warns = _warns(audit.scan(text))
            self.assertEqual(
                [], warns,
                f'{name} raised WARN findings (false positive): '
                f'{[w["rule"] for w in warns]}')


class MaliciousCorpusTest(unittest.TestCase):
    def test_malicious_samples_raise_at_least_one_warn(self):
        samples = _samples('malicious')
        self.assertTrue(samples, 'malicious corpus is empty')
        for name, text in samples:
            warns = _warns(audit.scan(text))
            self.assertTrue(
                warns,
                f'{name} raised no WARN findings — detection gap')


if __name__ == '__main__':
    unittest.main()
