import re
from typing import Dict, List, Set

RE_PKGBUILD_OPTDEPS = re.compile(r"optdepends = (.+)")
RE_PKGBUILD_OPTDEPS_x86_64 = re.compile(r"optdepends_x86_64 = (.+)")
RE_PKGBUILD_OPTDEPS_i686 = re.compile(r"optdepends_i686 = (.+)")


def read_optdeps_as_dict(srcinfo: str, x86_64: bool) -> dict:
    res = {}
    for optdep in read_optdeps(srcinfo, x86_64):
        split_dep = optdep.split(':')
        res[split_dep[0].strip()] = split_dep[1].strip() if len(split_dep) > 1 else None

    return res


def read_optdeps(srcinfo: str, x86_64: bool) -> Set[str]:
    optdeps = set(RE_PKGBUILD_OPTDEPS.findall(srcinfo))

    if x86_64:
        optdeps.update(set(RE_PKGBUILD_OPTDEPS_x86_64.findall(srcinfo)))
    else:
        optdeps.update(set(RE_PKGBUILD_OPTDEPS_i686.findall(srcinfo)))

    return optdeps


# --- PKGBUILD metadata extraction (for the first-class viewer) ----------------------------
# Pure, advisory parsers used by the PKGBUILD viewer to surface the "who/where/checksums" summary
# next to the source. Best-effort: a PKGBUILD is bash, not a strict format, so these only handle the
# common, idiomatic shapes and never raise.

_RE_HEADER_FIELD = re.compile(r'^#\s*(Maintainer|Contributor)\s*:\s*(.+?)\s*$', re.I)
_RE_PKGVER = re.compile(r'^\s*pkgver\s*=\s*(.+?)\s*$')
_RE_URL = re.compile(r'^\s*url\s*=\s*(.+?)\s*$')
_RE_PROTO_URL = re.compile(r'(?:https?|ftp|git\+https?|git)://[^\s\'"()]+')
_RE_CHECKSUM_ARRAY = re.compile(r"^\s*((?:sha(?:1|224|256|384|512)|b2|md5)sums(?:_\w+)?)\s*=\s*\((.*)",
                                re.I | re.DOTALL)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] in '"\'' and value[-1] == value[0]:
        return value[1:-1]
    return value


def _collect_array_body(lines: List[str], start: int) -> str:
    """Join an array assignment that may span several lines until the closing ')'."""
    body = []
    for ln in lines[start:]:
        body.append(ln)
        if ')' in ln:
            break
    text = '\n'.join(body)
    inner = text[text.find('(') + 1:]
    close = inner.rfind(')')
    return inner[:close] if close != -1 else inner


def parse_metadata(text: str) -> Dict:
    """Advisory metadata for the PKGBUILD viewer.

    Returns ``{maintainer, contributors, pkgver, url, sources, checksums}`` where ``sources`` is a
    list of upstream URLs (``name::`` prefixes stripped) and ``checksums`` is a list of
    ``{algo, value, skip}`` (``skip`` True for ``SKIP`` entries). Pure; never raises.
    """
    data: Dict = {'maintainer': None, 'contributors': [], 'pkgver': None, 'url': None,
                  'sources': [], 'checksums': []}
    if not text:
        return data

    lines = text.splitlines()
    for idx, raw in enumerate(lines):
        m = _RE_HEADER_FIELD.match(raw)
        if m:
            field, value = m.group(1).lower(), m.group(2).strip()
            if field == 'maintainer' and not data['maintainer']:
                data['maintainer'] = value
            elif field == 'contributor':
                data['contributors'].append(value)
            continue

        if data['pkgver'] is None:
            mv = _RE_PKGVER.match(raw)
            if mv:
                data['pkgver'] = _unquote(mv.group(1))
                continue

        if data['url'] is None:
            mu = _RE_URL.match(raw)
            if mu:
                data['url'] = _unquote(mu.group(1))
                continue

    # source=() — may be multi-line and array-suffixed (source_x86_64=...).
    for idx, raw in enumerate(lines):
        if re.match(r'^\s*source(?:_\w+)?\s*=\s*\(', raw):
            body = _collect_array_body(lines, idx)
            for tok in _RE_PROTO_URL.findall(body):
                if tok not in data['sources']:
                    data['sources'].append(tok)

    # *sums=() arrays — record which algos are present and whether any are SKIP'd.
    for idx, raw in enumerate(lines):
        m = _RE_CHECKSUM_ARRAY.match(raw)
        if m:
            algo = re.sub(r'sums(?:_\w+)?$', '', m.group(1).lower())
            body = _collect_array_body(lines, idx)
            entries = re.findall(r"'([^']*)'|\"([^\"]*)\"|(\S+)", body)
            for a, b, c in entries:
                val = a or b or c
                if not val or val == ')':
                    continue
                data['checksums'].append({'algo': algo, 'value': val,
                                          'skip': val.upper() == 'SKIP'})
    return data
