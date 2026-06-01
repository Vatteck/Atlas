"""map_srcinfo: pure-Python `.SRCINFO` parsing."""

from unittest import TestCase

from atlas.gems.arch.srcinfo import map_srcinfo


# Split-package .SRCINFO: pkgbase-level version fields + two subpackages with their own
# depends, multiline list fields, and a mix of scalar/list keys.
SRCINFO = """pkgbase = mypkg
\tpkgver = 2.0
\tpkgrel = 3
\tepoch = 1
\tdepends = glibc
\tdepends = gcc-libs
\tmakedepends = cmake
\tprovides = libfoo
\tsource = https://example.com/x.tar.gz

pkgname = mypkg
\tdepends = extra-dep

pkgname = mypkg-docs
\tdepends = man-db
"""


def _normalize(result: dict) -> dict:
    return {k: (sorted(v) if isinstance(v, (list, set)) else v) for k, v in result.items()}


class SrcinfoTest(TestCase):

    def test_values_for_pkgname(self):
        res = map_srcinfo(SRCINFO, pkgname='mypkg')
        self.assertEqual(res['pkgver'], '2.0')
        self.assertEqual(res['pkgrel'], '3')
        self.assertEqual(res['epoch'], '1')
        # pkgbase depends merge with the mypkg subpackage's own depends
        self.assertEqual(sorted(res['depends']), ['extra-dep', 'gcc-libs', 'glibc'])

    def test_fields_filter(self):
        res = map_srcinfo(SRCINFO, pkgname='mypkg', fields={'pkgver', 'pkgrel', 'epoch'})
        self.assertEqual(_normalize(res), {'pkgver': '2.0', 'pkgrel': '3', 'epoch': '1'})

    def test_subpackage_isolation(self):
        # the docs subpackage shouldn't pull in mypkg's extra-dep
        res = map_srcinfo(SRCINFO, pkgname='mypkg-docs')
        self.assertIn('man-db', res['depends'])
        self.assertNotIn('extra-dep', res['depends'] if isinstance(res['depends'], (list, set)) else [res['depends']])
