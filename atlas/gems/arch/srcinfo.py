"""Native-first `.SRCINFO` parsing with a pure-Python fallback.

`map_srcinfo` was ported to Rust (`atlas_rs.map_srcinfo`) but, unlike the other native
paths, kept **no** Python fallback — `aur.py` imported it directly. A missing or broken
native module would therefore break the whole Arch gem at import time. This module
restores the original pure-Python implementation as a fallback and routes through
`native.load()` for consistency with the rest of the engine (and so `ATLAS_DISABLE_RS`
works here too). See `docs/ARCHITECTURE.md` §3 and the strangler-fig rule in AGENTS.md.
"""

import logging
import re
from typing import Optional, Set

from atlas.gems.arch import native

logger = logging.getLogger(__name__)

RE_SRCINFO_KEYS = re.compile(r'(\w+)\s+=\s+(.+)\n')

KNOWN_LIST_FIELDS = ('validpgpkeys', 'checkdepends', 'checkdepends_x86_64',
                     'checkdepends_i686', 'depends', 'depends_x86_64', 'depends_i686',
                     'optdepends', 'optdepends_x86_64', 'optdepends_i686', 'sha256sums',
                     'sha256sums_x86_64', 'sha512sums', 'sha512sums_x86_64', 'source',
                     'source_x86_64', 'source_i686', 'makedepends', 'makedepends_x86_64',
                     'makedepends_i686', 'provides', 'conflicts')


def _merge_subinfos(subinfos: list, pkgname: Optional[str] = None,
                    fields: Optional[Set[str]] = None) -> dict:
    info = {}
    for subinfo in subinfos:
        if not pkgname or subinfo.get('pkgname') in {None, pkgname}:
            for key, val in subinfo.items():
                if not fields or key in fields:
                    current_val = info.get(key)

                    if current_val is None:
                        info[key] = val
                    else:
                        if not isinstance(current_val, set):
                            current_val = {current_val}
                            info[key] = current_val

                        if isinstance(val, set):
                            current_val.update(val)
                        else:
                            current_val.add(val)

    for field in list(info.keys()):
        val = info.get(field)

        if isinstance(val, set):
            info[field] = [*val]

    return info


def _map_srcinfo_py(string: str, pkgname: Optional[str], fields: Optional[Set[str]] = None) -> dict:
    """Pure-Python `.SRCINFO` parser (the original implementation the Rust port replaced).
    Reference behaviour for, and fallback to, ``atlas_rs.map_srcinfo``."""
    subinfos, subinfo = [], {}
    key_fields = {'pkgname', 'pkgbase'}

    for field in RE_SRCINFO_KEYS.findall(string):
        key = field[0].strip()
        val = field[1].strip()

        if subinfo and key in key_fields:
            subinfos.append(subinfo)
            subinfo = {key: val}
        elif not fields or key in fields:
            if key not in subinfo:
                subinfo[key] = {val} if key in KNOWN_LIST_FIELDS else val
            else:
                if not isinstance(subinfo[key], set):
                    subinfo[key] = {subinfo[key]}

                subinfo[key].add(val)

    if subinfo:
        subinfos.append(subinfo)

    pkgnames = {s['pkgname'] for s in subinfos if 'pkgname' in s}
    return _merge_subinfos(
        subinfos=subinfos,
        pkgname=None if (not pkgname or len(pkgnames) == 1 or pkgname not in pkgnames) else pkgname,
        fields=fields,
    )


def map_srcinfo(string: str, pkgname: Optional[str] = None,
                fields: Optional[Set[str]] = None) -> dict:
    """Parse `.SRCINFO` text. Uses the native parser when available, else the Python
    fallback. Honours ATLAS_DISABLE_RS / ATLAS_RS_DEBUG via ``native``."""
    atlas_rs = native.load(logger)
    if atlas_rs is not None:
        try:
            return atlas_rs.map_srcinfo(string, pkgname, fields)
        except Exception:
            native.report_failure(logger, 'map_srcinfo')

    return _map_srcinfo_py(string, pkgname, fields)
