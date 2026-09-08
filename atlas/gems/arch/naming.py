import re
from typing import Iterable, Set

# Lowercase + strip these and two names compare on equal terms: the AUR index writes
# 'google-chrome' as 'googlechrome', a Flatpak calls the same app 'Google Chrome', and a
# user types 'google chrome'. Whitespace is included — that is what the old index-only
# rule (worker.RE_CLEAR_REPLACE, '[-_.]') was missing, and why multi-word queries missed.
RE_NAME_SEPARATORS = re.compile(r'[\s._-]')


def normalize_pkg_name(name: str) -> str:
    """Lowercase a package name and strip its separators so names and user queries compare
    on equal terms: 'Google Chrome', 'google-chrome' and 'google_chrome' all -> 'googlechrome'.

    Must stay in sync with normalizeName() in atlas/view/webview/main.js — the shared cases
    live in tests/fixtures/pkg_name_normalization.json and are asserted from both suites.

    This is NOT groupKey(): build-method suffixes are deliberately kept, so 'brave-bin'
    normalizes to 'bravebin' and a search for it still finds it.
    """
    if not name:
        return ''

    return RE_NAME_SEPARATORS.sub('', str(name).lower())


def match_index_names(query: str, index: dict, limit: int = 25) -> Set[str]:
    """Real AUR package names whose normalized index key contains the normalized query.

    'index' maps normalized-key -> real name (AURClient.read_local_index()). The key is
    normalized again on read: worker.py writes it separator-stripped but not lowercased,
    and normalizing both sides here means a future index-format change cannot silently
    reintroduce the asymmetry this function exists to fix.
    """
    norm_query = normalize_pkg_name(query)

    if not norm_query or not index:
        return set()

    matched = set()

    for norm_name, real_name in index.items():
        if norm_query in normalize_pkg_name(norm_name):
            matched.add(real_name)

            if len(matched) == limit:
                break

    return matched


def any_name_matches(query: str, names: Iterable[str]) -> bool:
    """True if any of 'names' normalized-contains the normalized query.

    Used to decide whether an AUR RPC result set actually answers the query by name
    (vs. only by a description hit): the RPC's 'by=name-desc' search can return an
    unrelated package whose description merely contains the raw query string.
    """
    norm_query = normalize_pkg_name(query)

    if not norm_query or not names:
        return False

    return any(norm_query in normalize_pkg_name(name) for name in names)


def match_installed_names(query: str, installed: Iterable[str]) -> Set[str]:
    """Installed package names whose normalized name contains the normalized query.

    Normalizing both sides is what lets multi-word queries work: the caller used to skip
    this match entirely when the query held a space, because a raw multi-word substring
    can never occur in a package name.
    """
    norm_query = normalize_pkg_name(query)

    if not norm_query or not installed:
        return set()

    return {name for name in installed if norm_query in normalize_pkg_name(name)}
