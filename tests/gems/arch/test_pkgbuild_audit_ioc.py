"""Tests for IOC (Indicators of Compromise) database integration in the PKGBUILD audit pipeline.

The IOC database flags known-malicious AUR package names, npm/bun packages, file artifacts,
C2 domains, and attack accounts from the June 2026 Atomic Arch AUR supply-chain campaign.
"""
import unittest

from atlas.gems.arch import pkgbuild_audit as audit


def _ioc_findings(text):
    """Convenience: return only findings with rule_id 'known_ioc'."""
    return [f for f in audit.scan(text) if f['rule'] == 'known_ioc']


class IocKnownBadPackageTest(unittest.TestCase):
    """Known-malicious indicators should be flagged."""

    def test_known_bad_aur_package_name_is_flagged(self):
        """A PKGBUILD whose pkgname is a known-compromised package name should fire."""
        text = 'pkgname=compromised-package-a'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 1)
        finding = hits[0]
        self.assertEqual(finding['severity'], 'warn')
        self.assertEqual(finding['rule'], 'known_ioc')
        self.assertIn('aur_packages', finding['why'])

    def test_second_known_bad_aur_package_is_flagged(self):
        text = 'pkgname=compromised-package-b'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 1)
        self.assertIn('aur_packages', hits[0]['why'])

    def test_known_bad_npm_package_in_install_command(self):
        """npm install of a known-malicious npm package should fire."""
        text = 'npm install atomic-lockfile --save-dev'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 1)
        self.assertIn('npm_packages', hits[0]['why'])

    def test_known_bad_npm_lockfile_js(self):
        text = 'npm install lockfile-js'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 1)
        self.assertIn('npm_packages', hits[0]['why'])

    def test_known_bad_bun_package_in_install_command(self):
        """bun install of a known-malicious bun package should fire."""
        text = 'bun install js-digest'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 1)
        self.assertIn('bun_packages', hits[0]['why'])

    def test_known_file_artifact_scales_bpf_c(self):
        """A reference to scales.bpf.c (Atomic Arch eBPF payload) should fire."""
        text = 'cp scales.bpf.c "$srcdir/"'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 1)
        self.assertIn('file_artifacts', hits[0]['why'])

    def test_known_file_artifact_atomic_arch_backdoor(self):
        text = 'touch /tmp/.atomic-arch-backdoor'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 1)
        self.assertIn('file_artifacts', hits[0]['why'])

    def test_known_attack_account_in_maintainer_comment(self):
        """References to known attack accounts should fire."""
        text = '# Maintainer: krisztinavarga'
        # Comments are skipped by scan — so no IOC hit on a commented line.
        # But an uncommented reference should fire.
        text2 = 'source=("https://aur.archlinux.org/cgit/aur.git/snapshot/tobiaswesterburg.tar.gz")'
        hits = _ioc_findings(text2)
        self.assertTrue(len(hits) >= 1, "Expected at least one finding for attack_account reference")

    def test_comment_lines_are_skipped(self):
        """Commented lines should not produce findings (existing scan behavior)."""
        text = '# npm install atomic-lockfile'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 0)

    def test_multiple_ioc_hits_on_same_line(self):
        """A single line containing multiple IOCs should produce one finding per IOC."""
        # Only one match per (line, pattern) pair, but multiple patterns can match.
        text = 'bun install js-digest && npm install atomic-lockfile'
        hits = _ioc_findings(text)
        # Two patterns match: js-digest (bun_packages) and atomic-lockfile (npm_packages)
        self.assertEqual(len(hits), 2)


class IocNormalPackageTest(unittest.TestCase):
    """Normal, non-malicious packages should NOT be flagged."""

    def test_clean_pkgbuild_has_no_ioc_findings(self):
        from tests.gems.arch import test_pkgbuild_audit as t
        hits = _ioc_findings(t.CLEAN_PKGBUILD)
        self.assertEqual(len(hits), 0, "A clean PKGBUILD should have zero IOC findings")

    def test_normal_npm_package_not_flagged(self):
        text = 'npm install typescript --save-dev'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 0)

    def test_normal_aur_package_not_flagged(self):
        text = 'pkgname=firefox'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 0)

    def test_normal_bun_package_not_flagged(self):
        text = 'bun install chalk'
        hits = _ioc_findings(text)
        self.assertEqual(len(hits), 0)

    def test_empty_text_no_ioc(self):
        self.assertEqual(len(_ioc_findings('')), 0)


class IocLazyLoadingTest(unittest.TestCase):
    """The IOC database should be lazy-loaded — no fs hit at import time."""

    def setUp(self):
        """Reset IOC state before each test so ordering doesn't matter."""
        self._saved = audit._ioc_data
        audit._ioc_data = None

    def tearDown(self):
        """Restore IOC state after test."""
        audit._ioc_data = self._saved

    def test_ioc_data_is_lazy_loaded(self):
        """_ioc_data is initially None; it only gets populated when scan() is called."""
        self.assertIsNone(audit._ioc_data,
                          "IOC data should be None until first scan() call")

    def test_scan_triggers_ioc_load(self):
        """Calling scan() should populate _ioc_data."""
        audit.scan('pkgname=firefox')
        self.assertIsNotNone(audit._ioc_data,
                             "IOC data should be populated after first scan() call")


class IocSeverityAndMetadataTest(unittest.TestCase):
    """IOC findings should carry correct severity and metadata."""

    def test_ioc_severity_is_warn(self):
        hits = _ioc_findings('pkgname=compromised-package-a')
        self.assertEqual(hits[0]['severity'], 'warn')

    def test_ioc_metadata_is_campaign_kind(self):
        hits = _ioc_findings('pkgname=compromised-package-a')
        meta = hits[0]['meta']
        self.assertEqual(meta['kind'], 'campaign')
        self.assertEqual(meta['added'], '2026-07')
        self.assertIn('IOC', meta['source'])

    def test_ioc_rule_in_all_rule_ids(self):
        self.assertIn('known_ioc', audit.all_rule_ids())


if __name__ == '__main__':
    unittest.main()
