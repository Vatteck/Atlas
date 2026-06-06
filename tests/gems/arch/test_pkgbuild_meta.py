import unittest

from atlas.gems.arch import pkgbuild


SAMPLE = """\
# Maintainer: Jane Doe <jane@example.com>
# Contributor: Old Hand <old@example.com>
# Contributor: Someone Else
pkgname=demo
pkgver=1.4.0
pkgrel=2
url="https://demo.example.org"
source=("demo-$pkgver.tar.gz::https://files.example.org/demo-$pkgver.tar.gz"
        "fix.patch")
sha256sums=('deadbeef'
            'SKIP')
build() {
  make
}
"""


class ParseMetadataTest(unittest.TestCase):

    def test_empty_text(self):
        data = pkgbuild.parse_metadata('')
        self.assertIsNone(data['maintainer'])
        self.assertEqual([], data['sources'])

    def test_maintainer_and_contributors(self):
        data = pkgbuild.parse_metadata(SAMPLE)
        self.assertEqual('Jane Doe <jane@example.com>', data['maintainer'])
        self.assertEqual(['Old Hand <old@example.com>', 'Someone Else'], data['contributors'])

    def test_pkgver_and_url(self):
        data = pkgbuild.parse_metadata(SAMPLE)
        self.assertEqual('1.4.0', data['pkgver'])
        self.assertEqual('https://demo.example.org', data['url'])

    def test_sources_strip_name_prefix_and_skip_non_urls(self):
        data = pkgbuild.parse_metadata(SAMPLE)
        # the `name::url` form keeps only the URL; the local `fix.patch` is not a proto:// URL
        self.assertEqual(['https://files.example.org/demo-$pkgver.tar.gz'], data['sources'])

    def test_checksums_with_skip(self):
        data = pkgbuild.parse_metadata(SAMPLE)
        algos = {c['algo'] for c in data['checksums']}
        self.assertEqual({'sha256'}, algos)
        self.assertEqual(2, len(data['checksums']))
        self.assertTrue(any(c['skip'] for c in data['checksums']))
        self.assertTrue(any(not c['skip'] and c['value'] == 'deadbeef' for c in data['checksums']))

    def test_arch_suffixed_arrays(self):
        text = ("source_x86_64=(https://example.com/a.tar.gz)\n"
                "sha256sums_x86_64=('abc')\n")
        data = pkgbuild.parse_metadata(text)
        self.assertEqual(['https://example.com/a.tar.gz'], data['sources'])
        self.assertEqual('sha256', data['checksums'][0]['algo'])


class ParseInstallFilesTest(unittest.TestCase):

    def test_none_when_no_install(self):
        self.assertEqual([], pkgbuild.parse_install_files("pkgname=foo\n"))
        self.assertEqual([], pkgbuild.parse_install_files(''))

    def test_expands_pkgname_var(self):
        text = "pkgname=visual-studio-code-bin\ninstall=$pkgname.install\n"
        self.assertEqual(['visual-studio-code-bin.install'], pkgbuild.parse_install_files(text))

    def test_braced_var_and_quotes(self):
        text = "pkgname=foo\ninstall=\"${pkgname}.install\"\n"
        self.assertEqual(['foo.install'], pkgbuild.parse_install_files(text))

    def test_literal_filename(self):
        text = "install=scriptlet.install\n"
        self.assertEqual(['scriptlet.install'], pkgbuild.parse_install_files(text))

    def test_pkgbase_fallback(self):
        text = "install=$pkgbase.install\n"
        self.assertEqual(['mybase.install'], pkgbuild.parse_install_files(text, base='mybase'))

    def test_unresolved_var_dropped(self):
        # nothing to expand $missing → not a usable filename, dropped (never guess)
        self.assertEqual([], pkgbuild.parse_install_files("install=$missing.install\n"))

    def test_custom_underscore_var(self):
        text = "_name=bar\ninstall=$_name.install\n"
        self.assertEqual(['bar.install'], pkgbuild.parse_install_files(text))
