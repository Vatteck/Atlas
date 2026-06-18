"""Heuristic, AI-free scan of a PKGBUILD / .install for constructs worth a closer look.

**This is an advisory helper, not a safety verdict.** A clean result does NOT mean the package is
safe: the rules only catch known, *unobfuscated* patterns, are trivially evaded, and can throw
false positives. Never auto-block, and never show a "safe" badge based on this — the only goal is
to make the reader's eye stop on lines that deserve a second look.

Rules are plain pattern matchers (no model, no network). Each is tuned to avoid the common benign
cases (e.g. `rm -rf "$srcdir"`, `depends=('curl')`, hex checksums) so the signal stays useful.
"""
import re
from typing import Callable, List, Dict

DISCLAIMER = ("Heuristic hints only — NOT a safety check. A clean result does not mean the package "
              "is safe; these patterns are easily evaded and can be false alarms. Read the PKGBUILD.")

WARN = 'warn'
INFO = 'info'

# Rule provenance (see docs/plans/2026-06-16-audit-rule-maintenance.md).
#   EVERGREEN — a durable technique (reverse shell, credential theft, persistence) that stays
#               relevant regardless of any single incident.
#   CAMPAIGN  — added to catch a specific real-world incident; a candidate for *retirement* once
#               that campaign is dead, so it doesn't linger as low-signal noise.
EVERGREEN = 'evergreen'
CAMPAIGN = 'campaign'


def _has_base64_literal(line: str) -> bool:
    """A long base64-looking blob (contains +, / or = so we don't flag lowercase-hex checksums)."""
    for m in re.finditer(r'[A-Za-z0-9+/]{40,}={0,2}', line):
        tok = m.group(0)
        if '+' in tok or '/' in tok or tok.endswith('='):
            return True
    return False


def _has_insecure_http_source(line: str) -> bool:
    """A plain-http:// download (MITM risk). Skips git+http (git verifies via commit hash) and
    loopback hosts. The literal `http://` never matches inside `https://`, so TLS URLs are safe."""
    for m in re.finditer(r'(?P<git>git\+)?http://(?P<host>[^/\s"\'):]+)', line, re.I):
        if m.group('git'):
            continue
        if m.group('host').lower() in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
            continue
        return True
    return False


# (rule_id, severity, why, matcher) — matcher(line) -> truthy on a hit.
_RULES = [
    ('pipe_to_shell', WARN,
     'Pipes a download straight into a shell (runs remote code unconditionally).',
     re.compile(r'\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b|(?:ba|z)?sh\s+-c\s+["\']?\$\(|<\(\s*(?:curl|wget)', re.I).search),

    ('base64', WARN,
     'base64 is rarely needed in a PKGBUILD — inspect what is being encoded/decoded.',
     re.compile(r'\bbase64\b', re.I).search),

    ('base64_blob', INFO,
     'Long base64-looking literal — could be an embedded payload.',
     _has_base64_literal),

    ('eval', WARN,
     'eval runs a constructed string — inspect what it executes.',
     re.compile(r'\beval\b').search),

    ('hex_escapes', WARN,
     'Long hex-escape run — possible obfuscated payload.',
     re.compile(r'(?:\\x[0-9a-fA-F]{2}){4,}').search),

    ('network_cmd', WARN,
     'Network command in the build (sources should be declared in source=(), fetched by makepkg).',
     re.compile(r'\b(?:curl|wget|ncat|socat)\s+(?:-|\$|["\']?(?:https?|ftp|tftp)://)|/dev/tcp/', re.I).search),

    ('sensitive_path', WARN,
     'Touches sensitive user/system files (ssh, dotfiles, sudoers, crontab, autostart).',
     re.compile(r'\.ssh/|authorized_keys|\.bash(?:rc|_profile)|\.zshrc|\.profile\b|/etc/sudoers|crontab|autostart').search),

    ('setuid', WARN,
     'Sets a setuid/setgid bit.',
     re.compile(r'chmod\s+(?:[0-7]*[4267][0-7]{3}\b|[ugoa]*\+s\b)').search),

    ('sudo', WARN,
     'sudo inside a PKGBUILD — makepkg handles privilege escalation itself.',
     re.compile(r'\bsudo\b').search),

    ('rm_rf', WARN,
     'Recursive delete targeting $HOME or an absolute system path (not the build dir).',
     re.compile(r'\brm\s+-\w*[rR]\w*\s+["\']?(?:~|/|\$HOME|\$\{HOME)').search),

    # Atomic Arch (June 2026) campaign-specific patterns:
    ('npm_install_unknown', WARN,
     'npm/bun/pnpm/yarn install in build or install hook — the Atomic Arch (June 2026) '
     'supply-chain attack vector. Legitimate in build() for Node.js projects; highly suspicious '
     'in .install hooks or when installing packages not declared as build dependencies.',
     re.compile(r'\b(?:npm|bun|pnpm|yarn)\s+(?:install|i\b|add)\b', re.I).search),

    ('skip_checksum', INFO,
     'Checksum array contains SKIP — that source file is not cryptographically verified. '
     'Normal for VCS sources (git+, svn+, hg+); suspicious for binary or archive downloads.',
     re.compile(r"""['"]\s*SKIP\s*['"]""").search),

    ('temp_upload_service', INFO,
     'Reference to a temporary file-upload service — a known data-exfiltration channel '
     '(used by the Atomic Arch payload to send stolen credentials via temp.sh).',
     re.compile(r'\b(?:temp\.sh|transfer\.sh|0x0\.st|termbin\.com|pasteboard\.co)\b', re.I).search),

    ('systemd_service_install', INFO,
     'Enables or starts a systemd service. Normal for packages that ship daemons; '
     'review the bundled unit file for unexpected network access or persistence.',
     re.compile(r'\bsystemctl\s+(?:enable|start|daemon-reload)\b', re.I).search),

    # --- Reverse shells --- #
    ('reverse_shell_bash', WARN,
     'Bash-native reverse shell — a /dev/tcp (or /dev/udp) redirect, the classic '
     '"bash -i >& /dev/tcp/host/port" backdoor.',
     re.compile(r'>&\s*/dev/(?:tcp|udp)/|/dev/(?:tcp|udp)/[\w.-]+/\d+|bash\s+-i\b.*>&', re.I).search),

    ('reverse_shell_lang', WARN,
     'Language-level reverse-shell primitive (Python/Ruby/Perl/PHP socket call) — almost never '
     'belongs in a PKGBUILD.',
     re.compile(r'\bsocket\.connect\b|\bfsockopen\b|\bTCPSocket\b|\bIO\.popen\b|\bpty\.spawn\b', re.I).search),

    ('reverse_shell_listener', WARN,
     'Opens a listener (nc/ncat -l or socat LISTEN) — a bind shell / backdoor setup.',
     re.compile(r'\b(?:nc|ncat)\s+-[a-z]*l|\bsocat\b[^\n]*\bLISTEN\b', re.I).search),

    # --- Credential theft --- #
    ('credential_harvest', WARN,
     'Reads credential/keyring stores (shadow, GnuPG, keyring files, browser profiles, .netrc) — '
     'these have no business in a package build.',
     # Match credential *storage paths/files*, not bare daemon package names — `gnome-keyring`
     # and `kwallet` are common optdepends names, so matching them produced false positives.
     re.compile(r'/etc/g?shadow\b|\.gnupg\b|\.netrc\b'
                r'|\.local/share/keyrings\b|login\.keyring\b|/kwalletd/'
                r'|\.mozilla\b|\.config/(?:chromium|google-chrome|google-chrome-beta)\b', re.I).search),

    ('ssh_key_exfil', WARN,
     'A private SSH key (id_rsa/id_ed25519/id_ecdsa) on a line with a network command, pipe or '
     'redirect — reading a key is one thing, sending it is exfiltration.',
     re.compile(r'id_(?:rsa|ed25519|ecdsa)\b[^\n]*(?:\b(?:curl|wget|nc|ncat|socat)\b|[>|])'
                r'|\b(?:curl|wget|nc|ncat|socat)\b[^\n]*id_(?:rsa|ed25519|ecdsa)\b', re.I).search),

    # --- Persistence --- #
    ('systemd_timer_create', WARN,
     'Installs a systemd .timer unit — a more covert persistence vector than a plain service '
     '(a cron replacement that runs on a schedule).',
     re.compile(r'systemd/(?:system|user)/[^\s"\']+\.timer\b').search),

    ('cron_persist', WARN,
     'Installs a cron job (crontab -, /etc/cron.d, /var/spool/cron) — a persistence mechanism.',
     re.compile(r'\bcrontab\s+-|/etc/cron\.(?:d|hourly|daily|weekly)/|/var/spool/cron/').search),

    ('rc_local', WARN,
     'Writes /etc/rc.local or references rc-local.service — boot-time persistence.',
     re.compile(r'/etc/rc\.local\b|\brc-local\.service\b').search),

    ('shell_function_inject', WARN,
     'Appends to a user shell config (.bashrc/.zshrc/.profile) — injects code that runs on every '
     'shell start (distinct from merely reading these files).',
     re.compile(r'>>\s*["\']?\S*\.(?:bashrc|zshrc|bash_profile|profile)\b').search),

    # --- Obfuscation --- #
    ('printf_assembly', WARN,
     'Builds a string from octal/hex escapes via printf — a common way to hide a command before '
     'eval/sh.',
     re.compile(r'printf\s+["\']?(?:\\(?:x[0-9a-fA-F]{2}|[0-7]{2,3})){2,}', re.I).search),

    ('gzip_payload', INFO,
     'Decompresses (gzip -d/gunzip/zcat) straight into a shell — compressed-payload execution.',
     re.compile(r'\b(?:gzip\s+-\w*d|gunzip|zcat)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b', re.I).search),

    ('xxd_decode', WARN,
     'xxd -r reverses a hex dump — another decode-then-run obfuscation vector.',
     re.compile(r'\bxxd\s+-\w*r\b', re.I).search),

    # --- Dependency confusion --- #
    ('dep_confusion', WARN,
     'provides=/conflicts= lists a core system package — a takeover vector that can hijack or '
     'block an essential package.',
     re.compile(r'(?:provides|conflicts)\s*=\s*\([^)]*\b(?:glibc|coreutils|systemd|pacman|bash'
                r'|filesystem|linux|gcc-libs|glib2|util-linux|shadow|sudo|openssl|ca-certificates)\b',
                re.I).search),

    # --- Weak integrity --- #
    ('weak_checksum', INFO,
     'Uses md5sums/sha1sums — MD5 and SHA1 are cryptographically broken; prefer sha256/sha512/b2.',
     re.compile(r'\b(?:md5|sha1)sums\s*=').search),

    ('http_source', INFO,
     'A plain-http:// source download — vulnerable to MITM tampering; prefer https.',
     _has_insecure_http_source),

    # --- Privilege escalation --- #
    ('suid_capability', WARN,
     'setcap grants a dangerous file capability (cap_setuid, cap_sys_admin, cap_dac_override, …) '
     '— capability-based privilege escalation, subtler than chmod +s.',
     re.compile(r'\bsetcap\b[^\n]*\bcap_(?:setuid|setgid|net_raw|net_admin|sys_admin'
                r'|dac_override|dac_read_search|sys_ptrace|sys_module)\b', re.I).search),

    ('ld_preload', WARN,
     'LD_PRELOAD / /etc/ld.so.preload — library injection used by rootkits and keyloggers.',
     re.compile(r'\bLD_PRELOAD=|/etc/ld\.so\.preload\b').search),
]


# Provenance for rules we actually know the origin of, kept as a *side map* (keyed by rule id)
# rather than threaded into the tuples above — this keeps the security-sensitive regex lines
# untouched for a pure-bookkeeping change. Any rule absent here is the pre-metadata baseline: an
# evergreen pattern with no recorded source (the original hand-written set). See `rule_metadata()`.
#
# Honesty rule: only record `added`/`source` we genuinely know.
_KS_AUR_SOURCE = 'ks-aur-scanner rule categories (mapped to MITRE ATT&CK techniques), 2026-06-16'
_ATOMIC_ARCH_SOURCE = 'Atomic Arch (June 2026) AUR supply-chain campaign'
_STRUCTURAL_SOURCE = 'structural/semantic checks (docs/plans/2026-06-17-audit-structural-checks.md)'

_RULE_META: Dict[str, Dict] = {
    # Campaign rules — incident-specific, retire when the campaign is dead.
    'npm_install_unknown': {'kind': CAMPAIGN, 'added': '2026-06', 'source': _ATOMIC_ARCH_SOURCE},
    'temp_upload_service': {'kind': CAMPAIGN, 'added': '2026-06', 'source': _ATOMIC_ARCH_SOURCE},

    # Evergreen techniques mined from ks-aur-scanner's categories (Theme 1, 2026-06-16).
    'reverse_shell_bash': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'reverse_shell_lang': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'reverse_shell_listener': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'credential_harvest': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'ssh_key_exfil': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'systemd_timer_create': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'cron_persist': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'rc_local': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'shell_function_inject': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'printf_assembly': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'gzip_payload': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'xxd_decode': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'dep_confusion': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'weak_checksum': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'http_source': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'suid_capability': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},
    'ld_preload': {'kind': EVERGREEN, 'added': '2026-06-16', 'source': _KS_AUR_SOURCE},

    # Structural / semantic checks (whole-file), 2026-06-17.
    'network_in_package': {'kind': EVERGREEN, 'added': '2026-06-17', 'source': _STRUCTURAL_SOURCE},
    'unchecksummed_remote_source': {'kind': EVERGREEN, 'added': '2026-06-17', 'source': _STRUCTURAL_SOURCE},

    # Cross-file (.SRCINFO↔PKGBUILD) divergence, 2026-06-17.
    'srcinfo_source_divergence': {'kind': EVERGREEN, 'added': '2026-06-17', 'source': _STRUCTURAL_SOURCE},
}


def rule_metadata(rule_id: str) -> Dict:
    """Provenance for a rule id: {kind, added, source}. Rules with no recorded origin default to
    the pre-metadata baseline — evergreen, no known date/source — so every rule has metadata even
    though only the documented additions carry an `added`/`source`."""
    meta = _RULE_META.get(rule_id) or _EXTERNAL_META.get(rule_id)
    if meta is None:
        return {'kind': EVERGREEN, 'added': None, 'source': None}
    return {'kind': meta['kind'], 'added': meta.get('added'), 'source': meta.get('source')}


# --- Structural / semantic checks (whole-file, not per-line) ------------------------------------
# These look at field *relationships*, not surface patterns, so they're harder to evade and lower-FP
# than the regex rules. See docs/plans/2026-06-17-audit-structural-checks.md.

# A network fetch or pipe-to-shell — mirrors network_cmd + pipe_to_shell, reused inside package().
_NETWORK_FETCH_RE = re.compile(
    r'\b(?:curl|wget|ncat|nc|socat)\s+(?:-|\$|["\']?(?:https?|ftp|tftp)://)'
    r'|/dev/tcp/'
    r'|\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b'
    r'|<\(\s*(?:curl|wget)', re.I)


def _function_span(lines: List[str], name: str):
    """Return the (start, end) line indices (inclusive) spanning a bash function body, brace-matched.
    Handles `name() {`, `name ()`, and `function name`. None if the function isn't found.

    Caveat: braces are counted raw, so a `{`/`}` inside a string or comment (e.g. `echo "}"`) miscounts
    the span — an evasion that can end package() early. Accepted: this is advisory, a full bash parser
    is overkill, and a network call past the bad brace still trips the per-line pipe_to_shell/
    network_cmd rules — only the `network_in_package` *context* is lost, not the flag."""
    header = re.compile(rf'^\s*(?:function\s+)?{re.escape(name)}\s*\(\s*\)\s*\{{?'
                        rf'|^\s*function\s+{re.escape(name)}\b')
    for i, line in enumerate(lines):
        if not header.match(line):
            continue
        depth, started = 0, False
        for j in range(i, len(lines)):
            for ch in lines[j]:
                if ch == '{':
                    depth += 1
                    started = True
                elif ch == '}':
                    depth -= 1
                    if started and depth == 0:
                        return i, j
        return i, len(lines) - 1
    return None


def _network_in_package(text: str):
    """Hits for a network fetch / pipe-to-shell *inside* package(). package() should only install
    already-built files — fetching and running code there is a classic install-time backdoor."""
    lines = text.splitlines()
    span = _function_span(lines, 'package')
    if not span:
        return []
    start, end = span
    hits = []
    for idx in range(start, end + 1):
        stripped = lines[idx].strip()
        if not stripped or stripped.startswith('#'):
            continue
        if _NETWORK_FETCH_RE.search(lines[idx]):
            hits.append((idx + 1, stripped))
    return hits


def _split_array(body: str) -> List[str]:
    """Ordered array entries from a bash array body (quoted or bare), preserving position."""
    out = []
    for a, b, c in re.findall(r"'([^']*)'|\"([^\"]*)\"|(\S+)", body):
        val = a or b or c
        if val == ')':
            continue
        out.append(val)
    return out


def _collect_array(lines: List[str], start: int, first: str):
    """Accumulate an array body from its opening line until the line with the closing ')'.
    Returns (body_text, end_index)."""
    if ')' in first:
        return first[:first.index(')')], start
    parts = [first]
    for j in range(start + 1, len(lines)):
        ln = lines[j]
        if ')' in ln:
            parts.append(ln[:ln.index(')')])
            return ' '.join(parts), j
        parts.append(ln)
    return ' '.join(parts), len(lines) - 1


def _ordered_arrays(text: str):
    """Parse the plain `source=()` and `*sums=()` arrays preserving index alignment (arch-suffixed
    arrays like source_x86_64 are intentionally ignored in v1). Returns (source, source_line_no,
    sums) where sums is a list of ordered value lists."""
    lines = text.splitlines()
    source: List[str] = []
    source_line = 0
    sums: List[List[str]] = []
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        m_src = re.match(r'^\s*source\s*=\s*\((.*)', raw)
        m_sum = re.match(r'^\s*((?:sha(?:1|224|256|384|512)|b2|md5)sums)\s*=\s*\((.*)', raw)
        if m_src:
            body, j = _collect_array(lines, i, m_src.group(1))
            source = _split_array(body)
            source_line = i + 1
            i = j + 1
            continue
        if m_sum:
            body, j = _collect_array(lines, i, m_sum.group(2))
            sums.append(_split_array(body))
            i = j + 1
            continue
        i += 1
    return source, source_line, sums


def _is_remote_binary_source(entry: str) -> bool:
    """A remote http(s) download that is NOT a VCS source (git+/svn+/hg+/bzr+) — i.e. a tarball/
    binary whose integrity rests entirely on its checksum. Local-file and VCS sources are excluded."""
    url = entry.split('::', 1)[1] if '::' in entry else entry
    if re.match(r'^(?:git|svn|hg|bzr)\+', url, re.I):
        return False
    return bool(re.match(r'^https?://', url, re.I))


def _unchecksummed_remote_source(text: str):
    """Hits for a remote http(s) source whose checksum is explicitly SKIP — the maintainer (or an
    attacker who can reach the host) can swap the tarball with no integrity check. VCS and local-file
    sources are expected to SKIP and are never flagged.

    We flag only on an *explicit* SKIP at the aligned index, never on a merely *missing* checksum:
    makepkg requires a checksum per source, so 'no aligned value' means our v1 parser didn't see it
    (e.g. an arch-suffixed `sha256sums_x86_64` array we skip) — inconclusive, not unverified. Flagging
    on absence would false-positive a genuinely-checksummed source (a low-signal WARN that erodes
    trust in the badge)."""
    source, source_line, sums = _ordered_arrays(text)
    if not source:
        return []
    hits = []
    for i, entry in enumerate(source):
        if not _is_remote_binary_source(entry):
            continue
        # Look at the aligned checksum(s): real value → verified; explicit SKIP → flag; none parsed →
        # inconclusive (skip). If any *sums array verifies it, it's fine.
        verified = False
        skipped = False
        for arr in sums:
            if i < len(arr):
                val = arr[i].strip()
                if val.upper() == 'SKIP':
                    skipped = True
                elif val:
                    verified = True
                    break
        if skipped and not verified:
            hits.append((source_line, entry))
    return hits


# (rule_id, severity, why, analyzer) — analyzer(text) -> list of (line_no, line_text) hits.
_STRUCTURAL = [
    ('network_in_package', WARN,
     'Network fetch or pipe-to-shell inside package() — package() should only install already-built '
     'files; fetching and running code here is a classic install-time backdoor.',
     _network_in_package),

    ('unchecksummed_remote_source', WARN,
     'A remote http(s) source is not checksum-verified (SKIP/absent) — unlike a VCS source (pinned '
     'by commit) this tarball can be swapped at the host with no integrity check.',
     _unchecksummed_remote_source),
]


# --- .SRCINFO divergence (cross-file: needs both PKGBUILD and .SRCINFO) -------------------------
# .SRCINFO is what the AUR web page and most reviewers read; makepkg builds from the PKGBUILD. If a
# source host in the PKGBUILD isn't declared in .SRCINFO, the published metadata *hides where the
# build actually downloads from* — a real way to slip a malicious mirror past a reviewer. Host-level
# comparison is robust to the variable expansion that makes line-by-line source diffing noisy
# (paths carry $pkgver etc.; hosts are normally literal). See the structural-checks plan, step 3/4.
SRCINFO_DIVERGENCE_RULE = 'srcinfo_source_divergence'
_SRCINFO_DIVERGENCE_WHY = (
    "A source host in the PKGBUILD is not declared in .SRCINFO — .SRCINFO (what the AUR page and "
    "reviewers read) hides where this build actually downloads from. makepkg uses the PKGBUILD.")


def _host_of(entry: str):
    """The lowercased host of a source URL, or None for a local file / relative path. Strips a
    ``name::`` prefix and a VCS scheme prefix (git+/svn+/hg+/bzr+) so ``git+https://h/r`` → ``h``."""
    e = entry.split('::', 1)[1] if '::' in entry else entry
    e = re.sub(r'^(?:git|svn|hg|bzr)\+', '', e, flags=re.I)
    m = re.match(r'^[a-z][a-z0-9+.\-]*://(?:[^/@\s]*@)?([^/:\s\'"]+)', e, re.I)
    return m.group(1).lower() if m else None


def _pkgbuild_source_hosts(text: str):
    """Source hosts declared in the PKGBUILD, as a list of (host, line_no, line_text). Covers every
    ``source`` / ``source_<arch>`` array; skips hosts that still contain a ``$`` (unexpandable here)."""
    lines = text.splitlines()
    out = []
    seen = set()
    i, n = 0, len(lines)
    while i < n:
        m = re.match(r'^\s*source(?:_\w+)?\s*=\s*\((.*)', lines[i])
        if m:
            body, j = _collect_array(lines, i, m.group(1))
            for entry in _split_array(body):
                host = _host_of(entry)
                if host and '$' not in host and host not in seen:
                    seen.add(host)
                    out.append((host, i + 1, lines[i].strip()))
            i = j + 1
            continue
        i += 1
    return out


def _srcinfo_source_hosts(text: str):
    """Set of source hosts declared in a .SRCINFO (one ``source[_arch] = …`` per line, expanded)."""
    hosts = set()
    for line in text.splitlines():
        m = re.match(r'^\s*source(?:_\w+)?\s*=\s*(.+?)\s*$', line)
        if m:
            host = _host_of(m.group(1).strip())
            if host:
                hosts.add(host)
    return hosts


def scan_divergence(pkgbuild_text: str, srcinfo_text: str) -> List[Dict]:
    """Advisory findings for PKGBUILD↔.SRCINFO divergence. Empty list if either input is missing
    (we can only compare when both are present). Pure; never raises — it's advisory, not a gate."""
    if not pkgbuild_text or not srcinfo_text:
        return []
    try:
        declared = _srcinfo_source_hosts(srcinfo_text)
        if not declared:
            return []  # no parseable sources in .SRCINFO → nothing to compare against
        out: List[Dict] = []
        for host, line_no, line_text in _pkgbuild_source_hosts(pkgbuild_text):
            if host not in declared:
                out.append({'line_no': line_no, 'line': line_text,
                            'rule': SRCINFO_DIVERGENCE_RULE, 'severity': WARN,
                            'why': _SRCINFO_DIVERGENCE_WHY,
                            'meta': rule_metadata(SRCINFO_DIVERGENCE_RULE)})
        return out
    except Exception:
        return []


def all_rule_ids() -> set:
    """Every rule id the scanner can emit — per-line, structural, the cross-file divergence rule, and
    any registered external pack rules. Single source of truth for the metadata guard tests."""
    return ({rule_id for rule_id, *_ in _RULES}
            | {rule_id for rule_id, *_ in _STRUCTURAL}
            | {SRCINFO_DIVERGENCE_RULE}
            | {rule_id for rule_id, *_ in _EXTERNAL_RULES})


# --- External rules-pack (local, validated, fail-closed) ----------------------------------------
# An optional local JSON file can add *regex* rules without an app release. Strictly additive: a pack
# never edits/removes a bundled rule, and any problem degrades to fewer external rules (never a broken
# scan). Local-only/no-signing in this step; a remote pack would require signature verification.
# See docs/plans/2026-06-17-audit-rules-pack.md.
_EXTERNAL_RULES: List = []          # list of (rule_id, severity, why, matcher)
_EXTERNAL_META: Dict[str, Dict] = {}  # rule_id -> {kind, added, source}

_RULE_ID_RE = re.compile(r'^[a-z][a-z0-9_]*$')
_FLAG_MAP = {'i': re.IGNORECASE, 'm': re.MULTILINE, 's': re.DOTALL}
_MAX_PATTERN_LEN = 2000
_MAX_WHY_LEN = 500


def _bundled_rule_ids() -> set:
    """Rule ids defined in code (bundled) — a pack rule may not shadow any of these."""
    return ({rule_id for rule_id, *_ in _RULES}
            | {rule_id for rule_id, *_ in _STRUCTURAL}
            | {SRCINFO_DIVERGENCE_RULE})


def _validate_rule(raw, bundled: set, seen: set):
    """Validate one pack rule dict → (rule_tuple, meta) or None if it fails any check. Never raises."""
    try:
        if not isinstance(raw, dict):
            return None
        rid = raw.get('id')
        if not isinstance(rid, str) or not _RULE_ID_RE.match(rid) or len(rid) > 64:
            return None
        if rid in bundled or rid in seen:  # no shadowing a bundled rule, no in-pack dupes
            return None
        severity = raw.get('severity')
        if severity not in (WARN, INFO):
            return None
        why = raw.get('why')
        if not isinstance(why, str) or not why.strip() or len(why) > _MAX_WHY_LEN:
            return None
        pattern = raw.get('pattern')
        if not isinstance(pattern, str) or not pattern or len(pattern) > _MAX_PATTERN_LEN:
            return None
        flags = 0
        raw_flags = raw.get('flags', [])
        if not isinstance(raw_flags, list):
            return None
        for fl in raw_flags:
            if fl not in _FLAG_MAP:
                return None
            flags |= _FLAG_MAP[fl]
        matcher = re.compile(pattern, flags).search  # may raise re.error → caught below
        kind = raw.get('kind', EVERGREEN)
        if kind not in (EVERGREEN, CAMPAIGN):
            return None
        added = raw.get('added')
        source = raw.get('source')
        if added is not None and (not isinstance(added, str) or len(added) > 32):
            return None
        if source is not None and (not isinstance(source, str) or len(source) > 200):
            return None
        meta = {'kind': kind, 'added': added, 'source': source}
        return (rid, severity, why, matcher), meta
    except (re.error, TypeError, ValueError):
        return None


def load_rule_pack(obj) -> tuple:
    """Validate a parsed rules-pack object → (rules, meta). Pure; never raises. A bad top-level shape
    yields ([], {}); individual invalid rules are skipped (the valid ones still load)."""
    if not isinstance(obj, dict):
        return [], {}
    raw_rules = obj.get('rules')
    if not isinstance(raw_rules, list):
        return [], {}
    bundled = _bundled_rule_ids()
    seen: set = set()
    rules: List = []
    meta: Dict[str, Dict] = {}
    for raw in raw_rules:
        result = _validate_rule(raw, bundled, seen)
        if result is None:
            continue
        rule_tuple, rule_meta = result
        seen.add(rule_tuple[0])
        rules.append(rule_tuple)
        meta[rule_tuple[0]] = rule_meta
    return rules, meta


def register_rule_pack(obj) -> int:
    """Validate and register a pack's rules (additive). Returns the number of rules loaded."""
    rules, meta = load_rule_pack(obj)
    _EXTERNAL_RULES.extend(rules)
    _EXTERNAL_META.update(meta)
    return len(rules)


def reset_rule_packs() -> None:
    """Clear all registered external rules (back to the bundled-only set)."""
    _EXTERNAL_RULES.clear()
    _EXTERNAL_META.clear()


def load_rule_pack_file(path: str, logger=None) -> int:
    """Read, parse and register a local rules-pack JSON file. Fails closed: any error (missing file,
    bad JSON, …) registers nothing and returns 0. Never raises into the caller."""
    import json
    try:
        with open(path, encoding='utf-8') as fh:
            obj = json.load(fh)
    except FileNotFoundError:
        return 0
    except Exception as e:
        if logger is not None:
            logger.warning(f"Ignoring audit rules-pack at {path}: {e}")
        return 0
    count = register_rule_pack(obj)
    if logger is not None and count:
        logger.info(f"Loaded {count} external PKGBUILD-audit rule(s) from {path}")
    return count


def scan(text: str) -> List[Dict]:
    """Return advisory findings for the given PKGBUILD/.install text.

    Each finding: {line_no (1-based), line (stripped), rule, severity, why}. Pure-comment lines are
    skipped (inert, and a frequent false-positive source). Per-line regex rules run first, then the
    whole-file structural checks; the combined list is sorted by line number.
    """
    findings: List[Dict] = []
    if not text:
        return findings

    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith('#'):
            continue
        for rule_id, severity, why, matcher in _RULES:
            try:
                if matcher(raw):
                    findings.append({'line_no': idx, 'line': stripped,
                                     'rule': rule_id, 'severity': severity, 'why': why,
                                     'meta': rule_metadata(rule_id)})
            except Exception:
                continue  # a bad rule must never break the scan

        for rule_id, severity, why, matcher in _EXTERNAL_RULES:
            try:
                if matcher(raw):
                    findings.append({'line_no': idx, 'line': stripped,
                                     'rule': rule_id, 'severity': severity, 'why': why,
                                     'meta': rule_metadata(rule_id)})
            except Exception:
                continue  # an external rule must never break the scan

    for rule_id, severity, why, analyzer in _STRUCTURAL:
        try:
            for line_no, line_text in analyzer(text):
                findings.append({'line_no': line_no, 'line': line_text,
                                 'rule': rule_id, 'severity': severity, 'why': why,
                                 'meta': rule_metadata(rule_id)})
        except Exception:
            continue  # a bad structural check must never break the scan

    findings.sort(key=lambda f: f['line_no'])
    return findings


def diff(old_text: str, new_text: str, max_lines: int = 240) -> str:
    """Unified diff of two PKGBUILD revisions (what changed since the last build). Empty string if
    identical. Truncated to keep the advisory modal manageable."""
    import difflib
    old = (old_text or '').splitlines()
    new = (new_text or '').splitlines()
    lines = list(difflib.unified_diff(old, new, fromfile='PKGBUILD (last built)',
                                      tofile='PKGBUILD (new)', lineterm=''))
    if not lines:
        return ''
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f'... (diff truncated — {len(lines) - max_lines} more lines)']
    return '\n'.join(lines)


def diff_lines(old_text: str, new_text: str, max_lines: int = 240, annotate: bool = False) -> List[Dict]:
    """Structured unified diff for rich rendering: a list of {kind, text} where kind is
    'meta' (---/+++ file headers), 'hunk' (@@ … @@), 'add' (+), 'del' (-) or 'ctx' (unchanged).
    Empty list if identical. Truncated to keep the modal manageable.

    With `annotate=True`, each 'add' entry also carries `findings`: the `scan()` results (if
    any) for that exact line content — so the diff view can flag which *newly added* lines are
    the suspicious ones."""
    import difflib
    old = (old_text or '').splitlines()
    new = (new_text or '').splitlines()
    raw = list(difflib.unified_diff(old, new, fromfile='PKGBUILD (last built)',
                                    tofile='PKGBUILD (new)', lineterm=''))
    if not raw:
        return []

    findings_by_line: Dict[str, List[Dict]] = {}
    if annotate:
        for finding in scan(new_text):
            findings_by_line.setdefault(finding['line'], []).append(finding)

    truncated = len(raw) - max_lines if len(raw) > max_lines else 0
    out: List[Dict] = []
    for ln in raw[:max_lines]:
        if ln.startswith('+++') or ln.startswith('---'):
            kind = 'meta'
        elif ln.startswith('@@'):
            kind = 'hunk'
        elif ln.startswith('+'):
            kind = 'add'
        elif ln.startswith('-'):
            kind = 'del'
        else:
            kind = 'ctx'
        row = {'kind': kind, 'text': ln}
        if annotate and kind == 'add':
            row['findings'] = findings_by_line.get(ln[1:].strip(), [])
        out.append(row)
    if truncated:
        out.append({'kind': 'meta', 'text': f'… (diff truncated — {truncated} more lines)'})
    return out


def summarize(findings: List[Dict]) -> Dict:
    """Small rollup for the UI banner: counts by severity + total."""
    warn = sum(1 for f in findings if f['severity'] == WARN)
    info = sum(1 for f in findings if f['severity'] == INFO)
    return {'total': len(findings), 'warn': warn, 'info': info}
