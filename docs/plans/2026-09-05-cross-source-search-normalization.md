# Cross-source search normalization

**Date:** 2026-09-05
**Status:** design approved, not yet implemented
**Scope:** `atlas/gems/arch/` search matching. No UI changes.

---

## Problem

Searching `google chrome` returns only the Flatpak. Searching `chrome` returns a
correctly grouped AUR + Flatpak card. Same machine, same two installed packages.

The multi-source machinery is not at fault. `collapseByName()` and the "Available from
N sources" panel (`buildSourceCompareHTML`) both work — they are starved of input by a
search layer that matches only one naming dialect at a time. When search returns a
single source, every downstream surface degrades silently: no source pills, no compare
panel, and no indication that a second source exists. The user sees a confident
single-source card that is wrong.

### Root cause 1 — asymmetric normalization (AUR local index)

The AUR index is written with separators stripped
([`worker.py:192`](../../atlas/gems/arch/worker.py), `RE_CLEAR_REPLACE = re.compile(r'[\-_.]')`),
so `google-chrome` is stored under the key `googlechrome`.

The lookup ([`controller.py:343`](../../atlas/gems/arch/controller.py)) tests the **raw**
query against that normalized key:

```python
if query in norm_name:      # "google chrome" in "googlechrome"  -> False
                            # "chrome"        in "googlechrome"  -> True
```

The index is normalized; the query never is.

### Root cause 2 — installed matching skipped for multi-word queries

[`controller.py:367`](../../atlas/gems/arch/controller.py):

```python
if installed and ' ' not in query:
    matches.update((name for name in installed if query in name))
```

Any query containing a space skips installed-package matching entirely. The installed
AUR `google-chrome` was never considered for `google chrome` — excluded before ranking
or grouping ran. The guard is defensible given raw substring matching (a multi-word raw
substring is meaningless against package names); it becomes unnecessary once both sides
are normalized.

### Not a cause

- **Search fan-out.** [`controller.py:191`](../../atlas/view/core/controller.py) threads
  across every enabled manager. All sources are queried.
- **Result truncation.** [`api.py:1815`](../../atlas/view/webview/api.py) applies no limit.
  (It accepts a `pkg_type` parameter that is never used — dead, unrelated.)
- **`groupKey` breadth.** Real, but second-order; see Out of scope.

## Goals

1. `google chrome` returns the same result set as `chrome` for the AUR and installed legs.
2. One normalization rule, stated once per language, with a test that keeps the Python and
   JS sides in agreement.
3. No UI changes. Grouping, pills, and the compare panel recover on their own.

## Non-goals

- Changing the repo (`pacman -Ss`) query. It ANDs its terms across name *and* description,
  so it degrades gracefully on multi-word input. It also reaches a `shell=True` command via
  string concatenation ([`system.py:259`](../../atlas/commons/system.py),
  [`pacman.py:513`](../../atlas/gems/arch/pacman.py)) guarded only by denylist sanitization —
  a reason not to start rewriting that query string as a side effect of this work.
- Changing the AUR RPC query. `aur_client.search(query)` runs first and does its own
  full-text matching; the local index is the fallback. Normalizing for the RPC would likely
  hurt (`googlechrome` is a worse RPC query than `chrome`).
- Broadening `groupKey` to bridge vendor prefixes / descriptive suffixes.

## Design

### 1. Shared normalizer

A single function, the Python counterpart of `groupKey`'s separator handling:

```python
def normalize_pkg_name(name: str) -> str:
    """Lowercase and strip separators so package names and user queries compare on
    equal terms: 'Google Chrome', 'google-chrome' and 'google_chrome' all -> 'googlechrome'.
    Must stay in sync with groupKey() in view/webview/main.js."""
```

Rule: lowercase, then remove all of `[\s._-]`.

This **widens** the existing index rule (`[-_.]`) by adding whitespace. Both sides of every
comparison get it, so the index build and the lookup stay consistent.

Placement: a new `atlas/gems/arch/naming.py`, following the existing one-module-per-concern
pattern in the gem (cf. `sorting.py`). Not `__init__.py` — that file holds paths and
constants. Not `commons/` until a second gem needs it. Both consumers (`worker.py`,
`controller.py`) already import from within the gem, so no cycle risk.

### 2. AUR index lookup

`_fill_aur_search_results` normalizes the query once, before the loop, and compares against
the index key. Index keys are already separator-stripped but not lowercased — normalize the
key on read too rather than assuming, so a future index-format change cannot silently
reintroduce the asymmetry.

### 3. Installed matching

`__fill_search_installed_and_matched` drops the `' ' not in query` guard and matches
normalized-to-normalized.

### 4. Keeping the two languages honest

`RE_CLEAR_REPLACE` (worker.py, index build), `groupKey` (main.js, grouping), and
`normalize_pkg_name` must agree. They currently do not — `groupKey` strips whitespace,
`RE_CLEAR_REPLACE` does not.

A shared fixture list of input → expected-key pairs, asserted from both the Python suite and
the JS contract suite. Without it this bug regrows the next time one side is edited alone.

The index build itself should use `normalize_pkg_name` rather than its own regex, so there is
one implementation in Python instead of two. Note this changes the on-disk index key format
(keys become lowercased): the index is a regenerable cache under `ARCH_CACHE_DIR`, and reads
normalize the key anyway, so a stale index degrades to today's behaviour rather than breaking.

## Testing

TDD the normalizer — "which names should match" is a question better pinned by a table of
cases than by prose.

**Normalizer unit tests** — a case table:

| input | expected |
|---|---|
| `google-chrome` | `googlechrome` |
| `Google Chrome` | `googlechrome` |
| `google_chrome` | `googlechrome` |
| `visual-studio-code-bin` | `visualstudiocodebin` |
| `` (empty) | `` |
| `None` | `` |

**Regression tests** (the two bugs, named as such):

- Query `google chrome` matches an installed AUR package named `google-chrome`.
- Query `google chrome` matches index key `googlechrome`.
- Query `chrome` still matches — the existing behaviour must not regress.

**Cross-language agreement:** the shared fixture asserted from both suites.

Full suite must stay green: 787 Python + 62 JS.

## Verification

Automated tests cannot confirm the user-visible outcome, since the defect was only visible
in the rendered GUI. **Needs a GUI eyeball** (Vatteck's to run):

1. Search `google chrome` → one card with `AUR ● Flatpak ●` pills, matching the `chrome`
   result.
2. Open it → "Available from 2 sources" panel present.
3. Search `chrome` → unchanged from today.

## Out of scope — follow-ups agreed for after this lands

1. **Relevance inversion.** `sortByRelevance` ([`main.js:412`](../../atlas/view/webview/main.js))
   has no source/type term, and its `votes` tiebreaker scores any package lacking the field
   (Arch repo, Flatpak, AppImage) as `-1` — below an AUR package with zero votes. At equal
   name relevance an unvoted AUR package outranks the official signed one. `aurVariant()` is
   also applied to non-AUR names, penalising any package ending in `-git`.
2. **`groupKey` breadth.** Measured 11/19 on realistic Arch-name/display-name pairs. Misses
   vendor prefixes (`Mozilla Thunderbird`), descriptive suffixes (`VLC media player`), Arch
   packaging suffixes (`libreoffice-fresh`), and abbreviations (`code` ≙ `Visual Studio Code`).
   Worth re-measuring after this lands — search hiding sources likely inflated the apparent
   frequency.

Both are independent of this change and of each other.
