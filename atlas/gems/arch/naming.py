import re

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
