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


def _has_base64_literal(line: str) -> bool:
    """A long base64-looking blob (contains +, / or = so we don't flag lowercase-hex checksums)."""
    for m in re.finditer(r'[A-Za-z0-9+/]{40,}={0,2}', line):
        tok = m.group(0)
        if '+' in tok or '/' in tok or tok.endswith('='):
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
]


def scan(text: str) -> List[Dict]:
    """Return advisory findings for the given PKGBUILD/.install text.

    Each finding: {line_no (1-based), line (stripped), rule, severity, why}. Pure-comment lines are
    skipped (inert, and a frequent false-positive source). Sorted by line number.
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
                                     'rule': rule_id, 'severity': severity, 'why': why})
            except Exception:
                continue  # a bad rule must never break the scan
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


def diff_lines(old_text: str, new_text: str, max_lines: int = 240) -> List[Dict]:
    """Structured unified diff for rich rendering: a list of {kind, text} where kind is
    'meta' (---/+++ file headers), 'hunk' (@@ … @@), 'add' (+), 'del' (-) or 'ctx' (unchanged).
    Empty list if identical. Truncated to keep the modal manageable."""
    import difflib
    old = (old_text or '').splitlines()
    new = (new_text or '').splitlines()
    raw = list(difflib.unified_diff(old, new, fromfile='PKGBUILD (last built)',
                                    tofile='PKGBUILD (new)', lineterm=''))
    if not raw:
        return []
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
        out.append({'kind': kind, 'text': ln})
    if truncated:
        out.append({'kind': 'meta', 'text': f'… (diff truncated — {truncated} more lines)'})
    return out


def summarize(findings: List[Dict]) -> Dict:
    """Small rollup for the UI banner: counts by severity + total."""
    warn = sum(1 for f in findings if f['severity'] == WARN)
    info = sum(1 for f in findings if f['severity'] == INFO)
    return {'total': len(findings), 'warn': warn, 'info': info}
