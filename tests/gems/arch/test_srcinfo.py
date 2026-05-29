"""map_srcinfo: native vs the pure-Python fallback parity, and fallback correctness."""

from unittest import TestCase, skipUnless
from unittest.mock import patch

from atlas.gems.arch import srcinfo, native
from atlas.gems.arch.srcinfo import _map_srcinfo_py

try:
    from atlas.gems.arch import atlas_rs  # noqa: F401
    NATIVE_AVAILABLE = True
except ImportError:
    NATIVE_AVAILABLE = False


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


class SrcinfoFallbackTest(TestCase):

    def test_fallback_used_when_disabled(self):
        """With native disabled, map_srcinfo must return the pure-Python result."""
        with patch.object(native, '_RS_DISABLED', True):
            res = srcinfo.map_srcinfo(SRCINFO, pkgname='mypkg')
        self.assertEqual(_normalize(res), _normalize(_map_srcinfo_py(SRCINFO, 'mypkg')))

    def test_python_fallback_values(self):
        res = _map_srcinfo_py(SRCINFO, pkgname='mypkg')
        self.assertEqual(res['pkgver'], '2.0')
        self.assertEqual(res['pkgrel'], '3')
        self.assertEqual(res['epoch'], '1')
        self.assertEqual(sorted(res['depends']), ['extra-dep', 'gcc-libs', 'glibc'])

    def test_fields_filter_python(self):
        res = _map_srcinfo_py(SRCINFO, pkgname='mypkg', fields={'pkgver', 'pkgrel', 'epoch'})
        self.assertEqual(_normalize(res), {'pkgver': '2.0', 'pkgrel': '3', 'epoch': '1'})


@skipUnless(NATIVE_AVAILABLE, "atlas_rs not built; cannot verify native vs python parity")
class SrcinfoParityTest(TestCase):
    """The native and Python parsers must agree (the fallback is a faithful drop-in)."""

    def _assert_parity(self, pkgname, fields):
        with patch.object(native, '_RS_DISABLED', False):
            native_res = srcinfo.map_srcinfo(SRCINFO, pkgname=pkgname, fields=fields)
        py_res = _map_srcinfo_py(SRCINFO, pkgname, fields)
        self.assertEqual(_normalize(native_res), _normalize(py_res),
                         f"divergence for pkgname={pkgname!r} fields={fields!r}")

    def test_parity_no_fields(self):
        self._assert_parity('mypkg', None)

    def test_parity_version_fields(self):
        # the real controller.py use case: get version data for a specific package
        self._assert_parity('mypkg', {'pkgver', 'pkgrel', 'epoch'})

    def test_parity_pkgname_field(self):
        self._assert_parity(None, {'pkgname'})
