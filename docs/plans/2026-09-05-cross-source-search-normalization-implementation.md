# Cross-Source Search Normalization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Design doc:** [2026-09-05-cross-source-search-normalization.md](2026-09-05-cross-source-search-normalization.md)
— read it first; it explains why this bug exists and what is deliberately out of scope.

**Goal:** Make `google chrome` find the AUR package `google-chrome`, so multi-source grouping
and the "Available from N sources" panel stop being starved of input.

**Architecture:** One name-normalization rule (lowercase, strip `[\s._-]`) applied to *both*
sides of every name comparison in the arch gem's search path. The matching logic moves out of
the 220 KB `controller.py` into a new focused `naming.py` as pure functions, which makes it
testable without mocking `aur_client`. A shared JSON fixture keeps the Python and JS
normalizers from drifting apart.

**Tech Stack:** Python 3.10–3.14 (stdlib `re`, `unittest.TestCase` run under pytest),
plain JS run by `node --test`.

## Global Constraints

- **Pure Python.** No Rust, no Qt, no new runtime dependencies (AGENTS.md §3.1–3.2).
- **PEP 8**; match the surrounding file's comment density and idiom.
- **Conventional commits**, one logical change each, ending with the `Co-Authored-By:` trailer.
- **Branch:** `master`. Run `git branch` to confirm rather than trusting this line.
- **Full suite green before each commit:** `python -m pytest` (787 tests) and
  `node --test tests/view/webview/main_js_contracts.test.js` (62 tests).
- **Do not touch** `atlas/gems/arch/pacman.py` or `atlas/commons/system.py` — a separate
  session is hardening `pacman.search` against shell injection in those files concurrently.
- **The normalization rule is exactly:** lowercase, then remove every character matching
  `[\s._-]`. Nothing else. Build-method suffix stripping is NOT part of it.

---

## File Structure

| File | Responsibility |
|---|---|
| `atlas/gems/arch/naming.py` | **Create.** The normalization rule and the two pure matching functions. Sole owner of "do these two names refer to the same package?" in Python. |
| `tests/gems/arch/test_naming.py` | **Create.** Unit tests for all three functions plus the shared fixture. |
| `tests/fixtures/pkg_name_normalization.json` | **Create.** Input→expected pairs asserted by both the Python and JS suites. |
| `atlas/gems/arch/controller.py` | **Modify.** Two call sites delegate to `naming.py`. No logic added here. |
| `atlas/gems/arch/worker.py` | **Modify.** Index build uses the shared normalizer instead of its own regex. |
| `atlas/view/webview/main.js` | **Modify.** Extract `normalizeName()` out of `groupKey()`; export it for tests. |
| `tests/view/webview/main_js_contracts.test.js` | **Modify.** One new test asserting the shared fixture. |

---

## Task 1: The normalizer and its fixture

**Files:**
- Create: `atlas/gems/arch/naming.py`
- Create: `tests/gems/arch/test_naming.py`
- Create: `tests/fixtures/pkg_name_normalization.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `atlas.gems.arch.naming.normalize_pkg_name(name: str) -> str` — lowercases and
  strips `[\s._-]`. Returns `''` for `None` or `''`. Used by every later task.

- [ ] **Step 1: Write the shared fixture**

Create `tests/fixtures/pkg_name_normalization.json`. These cases are asserted from both the
Python and the JS suite, so they may only cover separator/case normalization — no
build-suffix stripping.

```json
{
  "comment": "Shared cases for the package-name normalization rule: lowercase, then strip [\\s._-]. Asserted by tests/gems/arch/test_naming.py (normalize_pkg_name) and tests/view/webview/main_js_contracts.test.js (normalizeName). Both must agree. Build-method suffix stripping is NOT part of this rule and must not appear here.",
  "cases": [
    {"input": "google-chrome", "expected": "googlechrome"},
    {"input": "Google Chrome", "expected": "googlechrome"},
    {"input": "google_chrome", "expected": "googlechrome"},
    {"input": "GOOGLE.CHROME", "expected": "googlechrome"},
    {"input": "  Google  Chrome  ", "expected": "googlechrome"},
    {"input": "visual-studio-code-bin", "expected": "visualstudiocodebin"},
    {"input": "brave-bin", "expected": "bravebin"},
    {"input": "Sublime Text", "expected": "sublimetext"},
    {"input": "sublime-text", "expected": "sublimetext"},
    {"input": "vlc", "expected": "vlc"},
    {"input": "", "expected": ""}
  ]
}
```

Note `brave-bin` → `bravebin`. This is deliberate and is the difference between this rule and
`groupKey`. A search for `brave-bin` must still find `brave-bin`.

- [ ] **Step 2: Write the failing test**

Create `tests/gems/arch/test_naming.py`. Match the existing `unittest.TestCase` style used by
`tests/gems/arch/test_sorting.py`.

```python
import json
import os
from unittest import TestCase

from atlas.gems.arch import naming

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), '..', '..',
                            'fixtures', 'pkg_name_normalization.json')


def load_fixture_cases():
    with open(os.path.abspath(FIXTURE_PATH)) as f:
        return json.load(f)['cases']


class NormalizePkgNameTest(TestCase):

    def test_shared_fixture_cases(self):
        cases = load_fixture_cases()
        self.assertTrue(cases, 'fixture must not be empty')

        for case in cases:
            with self.subTest(input=case['input']):
                self.assertEqual(case['expected'],
                                 naming.normalize_pkg_name(case['input']))

    def test_none_returns_empty_string(self):
        self.assertEqual('', naming.normalize_pkg_name(None))

    def test_build_suffix_is_not_stripped(self):
        # groupKey() in main.js strips build suffixes; this rule must not, or a search
        # for 'brave-bin' would stop finding brave-bin.
        self.assertEqual('bravebin', naming.normalize_pkg_name('brave-bin'))
        self.assertNotEqual(naming.normalize_pkg_name('brave'),
                            naming.normalize_pkg_name('brave-bin'))
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
python -m pytest tests/gems/arch/test_naming.py -v
```

Expected: FAIL — `ImportError: cannot import name 'naming' from 'atlas.gems.arch'`.

- [ ] **Step 4: Write the minimal implementation**

Create `atlas/gems/arch/naming.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
python -m pytest tests/gems/arch/test_naming.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add atlas/gems/arch/naming.py tests/gems/arch/test_naming.py tests/fixtures/pkg_name_normalization.json
git commit -m "feat(arch): add shared package-name normalizer

Lowercase + strip [\s._-], the rule the AUR index build already applied to
its keys but never to the query. Shared fixture so the JS side can assert
the same cases.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: `match_index_names` — the AUR index lookup

**Files:**
- Modify: `atlas/gems/arch/naming.py`
- Modify: `tests/gems/arch/test_naming.py`

**Interfaces:**
- Consumes: `normalize_pkg_name` from Task 1.
- Produces: `naming.match_index_names(query: str, index: dict, limit: int = 25) -> Set[str]`.
  `index` maps normalized-key → real-package-name, as returned by
  `AURClient.read_local_index()`. Returns at most `limit` real names. Task 4 calls this.

- [ ] **Step 1: Write the failing test**

Append to `tests/gems/arch/test_naming.py`:

```python
class MatchIndexNamesTest(TestCase):

    # Keys as read_local_index() returns them: worker.py strips [-_.] when writing.
    INDEX = {
        'googlechrome': 'google-chrome',
        'googlechromebeta': 'google-chrome-beta',
        'curlimpersonate': 'curl-impersonate',
        'vlc': 'vlc',
    }

    def test_multi_word_query_matches_hyphenated_name(self):
        # The reported bug: 'google chrome' found nothing because the raw query was
        # tested against an already-normalized key.
        self.assertIn('google-chrome', naming.match_index_names('google chrome', self.INDEX))

    def test_single_word_query_still_matches(self):
        # Regression guard: this worked before and must keep working.
        matched = naming.match_index_names('chrome', self.INDEX)
        self.assertIn('google-chrome', matched)
        self.assertIn('google-chrome-beta', matched)

    def test_case_and_separator_insensitive(self):
        self.assertIn('google-chrome', naming.match_index_names('Google_Chrome', self.INDEX))

    def test_empty_query_matches_nothing(self):
        self.assertEqual(set(), naming.match_index_names('', self.INDEX))

    def test_empty_index_matches_nothing(self):
        self.assertEqual(set(), naming.match_index_names('chrome', {}))

    def test_none_index_matches_nothing(self):
        self.assertEqual(set(), naming.match_index_names('chrome', None))

    def test_respects_limit(self):
        index = {f'pkg{i}': f'pkg-{i}' for i in range(50)}
        self.assertEqual(5, len(naming.match_index_names('pkg', index, limit=5)))

    def test_default_limit_is_25(self):
        index = {f'pkg{i}': f'pkg-{i}' for i in range(50)}
        self.assertEqual(25, len(naming.match_index_names('pkg', index)))
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/gems/arch/test_naming.py::MatchIndexNamesTest -v
```

Expected: FAIL — `AttributeError: module 'atlas.gems.arch.naming' has no attribute 'match_index_names'`.

- [ ] **Step 3: Write the minimal implementation**

Add `from typing import Set` below the `import re` line in `atlas/gems/arch/naming.py`, then
append:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/gems/arch/test_naming.py -v
```

Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/gems/arch/naming.py tests/gems/arch/test_naming.py
git commit -m "feat(arch): add match_index_names for AUR index lookup

Normalizes both the query and the index key, so 'google chrome' matches
the key 'googlechrome'. Preserves the existing 25-result cap.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: `match_installed_names` — installed-package matching

**Files:**
- Modify: `atlas/gems/arch/naming.py`
- Modify: `tests/gems/arch/test_naming.py`

**Interfaces:**
- Consumes: `normalize_pkg_name` from Task 1.
- Produces: `naming.match_installed_names(query: str, installed: Iterable[str]) -> Set[str]`.
  No limit — the caller already bounds this by the installed set. Task 4 calls this.

- [ ] **Step 1: Write the failing test**

Append to `tests/gems/arch/test_naming.py`:

```python
class MatchInstalledNamesTest(TestCase):

    INSTALLED = {'google-chrome', 'curl-impersonate', 'vlc', 'firefox'}

    def test_multi_word_query_matches(self):
        # The reported bug: controller.py skipped installed matching entirely when the
        # query contained a space, so an installed google-chrome was never considered.
        self.assertEqual({'google-chrome'},
                         naming.match_installed_names('google chrome', self.INSTALLED))

    def test_single_word_query_still_matches(self):
        self.assertEqual({'google-chrome'},
                         naming.match_installed_names('chrome', self.INSTALLED))

    def test_case_insensitive(self):
        self.assertEqual({'firefox'}, naming.match_installed_names('FireFox', self.INSTALLED))

    def test_no_match_returns_empty(self):
        self.assertEqual(set(), naming.match_installed_names('nonexistent', self.INSTALLED))

    def test_empty_query_matches_nothing(self):
        self.assertEqual(set(), naming.match_installed_names('', self.INSTALLED))

    def test_empty_installed_matches_nothing(self):
        self.assertEqual(set(), naming.match_installed_names('chrome', set()))

    def test_none_installed_matches_nothing(self):
        self.assertEqual(set(), naming.match_installed_names('chrome', None))
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/gems/arch/test_naming.py::MatchInstalledNamesTest -v
```

Expected: FAIL — no attribute `match_installed_names`.

- [ ] **Step 3: Write the minimal implementation**

Widen the typing import in `atlas/gems/arch/naming.py` to
`from typing import Iterable, Set`, then append:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/gems/arch/test_naming.py -v
```

Expected: PASS (18 tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/gems/arch/naming.py tests/gems/arch/test_naming.py
git commit -m "feat(arch): add match_installed_names

Normalized-to-normalized matching, which removes the need for the caller's
\"skip if the query has a space\" guard.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Wire both fixes into `controller.py`

**Files:**
- Modify: `atlas/gems/arch/controller.py` (two call sites, around lines 326–369)

**Interfaces:**
- Consumes: `naming.match_index_names`, `naming.match_installed_names` from Tasks 2–3.
- Produces: no new interface. Behaviour change only.

This is the task that actually fixes the user-visible bug. It adds no logic — it deletes
logic and delegates.

- [ ] **Step 1: Read the current code**

```bash
sed -n '326,369p' atlas/gems/arch/controller.py
```

Confirm both sites still look as described below before editing. If they don't, stop and
report — the design doc's line references may have drifted.

- [ ] **Step 2: Add the import**

Find the existing `from atlas.gems.arch import ...` line near the top of the file and add
`naming` to it, keeping the existing alphabetical order if the line has one. Do not add a
separate import statement if one already imports from that package.

- [ ] **Step 3: Replace the AUR index lookup**

In `_fill_aur_search_results`, replace this block:

```python
            aur_index = self.aur_client.read_local_index()
            if aur_index:
                self.logger.info("Querying through the local AUR index")
                to_query = set()
                for norm_name, real_name in aur_index.items():
                    if query in norm_name:
                        to_query.add(real_name)

                    if len(to_query) == 25:
                        break

                pkgs_found = self.aur_client.get_info(to_query)
```

with:

```python
            aur_index = self.aur_client.read_local_index()
            if aur_index:
                self.logger.info("Querying through the local AUR index")
                to_query = naming.match_index_names(query, aur_index)
                pkgs_found = self.aur_client.get_info(to_query)
```

- [ ] **Step 4: Replace the installed matching**

In `__fill_search_installed_and_matched`, replace:

```python
        if installed and ' ' not in query:  # already filling some matches only based on the query
            matches.update((name for name in installed if query in name))
```

with:

```python
        # Both sides normalized, so a multi-word query ('google chrome') matches a
        # hyphenated package name ('google-chrome'). The old raw-substring match could
        # not, which is why this used to be skipped whenever the query held a space.
        matches.update(naming.match_installed_names(query, installed))
```

- [ ] **Step 5: Run the full Python suite**

```bash
python -m pytest
```

Expected: PASS, 787 + 18 = 805 tests. If anything fails, the failure is real — the old
behaviour was being asserted somewhere. Read the failing test and report before changing it.

- [ ] **Step 6: Commit**

```bash
git add atlas/gems/arch/controller.py
git commit -m "fix(arch): match multi-word search queries against package names

Searching 'google chrome' returned only the Flatpak while 'chrome' returned
a grouped AUR+Flatpak card. Two causes, both in the arch gem's matching:
the AUR index lookup tested the raw query against an already-normalized key,
and installed matching was skipped outright for any query with a space.

Multi-source grouping and the source-compare panel were never broken; they
were starved of input.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: One normalizer in Python

**Files:**
- Modify: `atlas/gems/arch/worker.py` (line 39 `RE_CLEAR_REPLACE`, line 192 its use)

**Interfaces:**
- Consumes: `naming.normalize_pkg_name` from Task 1.
- Produces: no new interface. Index keys become lowercased.

`RE_CLEAR_REPLACE = re.compile(r'[\-_.]')` is a second, narrower copy of the rule. Two
implementations is how this bug regrows.

**On-disk impact:** index keys become lowercased. The index is a regenerable cache under
`ARCH_CACHE_DIR`, and `match_index_names` normalizes keys on read, so an index written by
an older build still works — it degrades to today's behaviour, not to breakage.

- [ ] **Step 1: Write the failing test**

Append to `tests/gems/arch/test_naming.py`:

```python
class WorkerIndexKeyTest(TestCase):

    def test_worker_writes_keys_with_the_shared_normalizer(self):
        # One rule, one implementation. A second copy of it in worker.py is how the
        # query/key asymmetry got introduced in the first place.
        from atlas.gems.arch import worker

        self.assertFalse(hasattr(worker, 'RE_CLEAR_REPLACE'),
                         'worker must use naming.normalize_pkg_name, not its own regex')
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/gems/arch/test_naming.py::WorkerIndexKeyTest -v
```

Expected: FAIL — `worker must use naming.normalize_pkg_name, not its own regex`.

- [ ] **Step 3: Make the change**

In `atlas/gems/arch/worker.py`:

Delete line 39:

```python
RE_CLEAR_REPLACE = re.compile(r'[\-_.]')
```

Add `naming` to the existing `from atlas.gems.arch import ...` line at the top of the file.

Replace line 192:

```python
                            f.write('{}={}\n'.format(RE_CLEAR_REPLACE.sub('', n), n))
```

with:

```python
                            f.write('{}={}\n'.format(naming.normalize_pkg_name(n), n))
```

Then check whether `re` is still used elsewhere in `worker.py`:

```bash
grep -n "re\." atlas/gems/arch/worker.py
```

If there are no remaining uses, remove the now-unused `import re`.

- [ ] **Step 4: Run the full Python suite**

```bash
python -m pytest
```

Expected: PASS, 806 tests.

- [ ] **Step 5: Commit**

```bash
git add atlas/gems/arch/worker.py tests/gems/arch/test_naming.py
git commit -m "refactor(arch): build the AUR index with the shared normalizer

Removes the second, narrower copy of the normalization rule. Index keys are
now lowercased too; the index is a regenerable cache and reads normalize the
key anyway, so an older index degrades rather than breaks.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Cross-language agreement

**Files:**
- Modify: `atlas/view/webview/main.js` (around lines 1538–1546, and the test-hooks export block near line 6911)
- Modify: `tests/view/webview/main_js_contracts.test.js`

**Interfaces:**
- Consumes: `tests/fixtures/pkg_name_normalization.json` from Task 1.
- Produces: `normalizeName(name)` on `window.__atlasTestHooks`, with
  `groupKey(name) === normalizeName(stripBuildSuffix(name))` still holding.

- [ ] **Step 1: Extract `normalizeName` in main.js**

Replace:

```js
function groupKey(name) {
    return stripBuildSuffix(name).toLowerCase().replace(/[\s._-]+/g, '');
}
```

with:

```js
// The separator/case half of grouping, on its own because Python needs the same rule:
// atlas/gems/arch/naming.py's normalize_pkg_name must agree with it, and the shared cases
// in tests/fixtures/pkg_name_normalization.json are asserted from both suites. Build-suffix
// stripping is deliberately NOT part of it — search must still find "brave-bin" by name.
function normalizeName(name) {
    return String(name == null ? '' : name).toLowerCase().replace(/[\s._-]+/g, '');
}

function groupKey(name) {
    return normalizeName(stripBuildSuffix(name));
}
```

- [ ] **Step 2: Export it for tests**

In the test-hooks export block (near line 6911, the object containing `groupKey`,
`stripBuildSuffix`, `collapseByName`), add `normalizeName,` immediately before `groupKey,`.

- [ ] **Step 3: Write the failing test**

Add this function to `tests/view/webview/main_js_contracts.test.js`, and add
`testNameNormalizationMatchesPython,` to the `tests` array at the bottom of the file:

```js
async function testNameNormalizationMatchesPython() {
  const { hooks } = loadMainJs({});
  const { normalizeName, groupKey, stripBuildSuffix } = hooks;

  // The shared rule, asserted from the same fixture the Python suite reads. If these two
  // drift apart, search stops finding what grouping merges.
  const fixture = JSON.parse(
    fs.readFileSync(path.join(process.cwd(), 'tests/fixtures/pkg_name_normalization.json'), 'utf8'));
  assert.ok(fixture.cases.length > 0, 'fixture must not be empty');

  for (const { input, expected } of fixture.cases) {
    assert.strictEqual(normalizeName(input), expected,
      `normalizeName(${JSON.stringify(input)}) must match Python's normalize_pkg_name`);
  }

  // normalizeName is only the separator/case half — build suffixes survive it.
  assert.strictEqual(normalizeName('brave-bin'), 'bravebin');
  assert.strictEqual(groupKey('brave-bin'), 'brave', 'groupKey still strips build suffixes');
  assert.strictEqual(groupKey('Google Chrome'), normalizeName(stripBuildSuffix('Google Chrome')),
    'groupKey is normalizeName composed with stripBuildSuffix');
}
```

- [ ] **Step 4: Run the JS suite to verify it fails, then passes**

```bash
node --test tests/view/webview/main_js_contracts.test.js
```

Before Step 1's edit this fails with `normalizeName is not a function`. After Steps 1–2 it
passes. If you did the steps in order, run it now and expect PASS.

Note: `node --test` reports `tests 1` — the file is one test wrapping an array of check
functions, each printing its own `✓` line. Confirm `fail 0` and a new
`✓ testNameNormalizationMatchesPython` line; do not look for a test count of 63.

- [ ] **Step 5: Run both suites**

```bash
python -m pytest && node --test tests/view/webview/main_js_contracts.test.js
```

Expected: 806 Python passed; JS `fail 0` with the new ✓ line present.

- [ ] **Step 6: Commit**

```bash
git add atlas/view/webview/main.js tests/view/webview/main_js_contracts.test.js
git commit -m "test(webview): assert JS and Python name normalization agree

Extracts normalizeName() out of groupKey() so the separator/case rule can be
asserted against the same fixture the Python suite reads. groupKey stays
normalizeName(stripBuildSuffix(name)).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Handoff

**Files:**
- Modify: `docs/STATUS.md`
- Modify: `docs/.last-agent`

- [ ] **Step 1: Update STATUS.md**

Add a "Done (recent)" entry describing the fix, and note the outstanding GUI verification.
Keep STATUS.md under ~200 lines (AGENTS.md §1) — move an older Done entry to HISTORY.md if
it has grown past that.

The entry must state that the fix is **not GUI-verified**, and list the manual pass:

1. Search `google chrome` → one card with `AUR ● Flatpak ●` pills, matching the `chrome` result.
2. Open it → "Available from 2 sources" panel present.
3. Search `chrome` → unchanged from today.

Also record the two agreed follow-ups from the design doc's "Out of scope" section
(relevance inversion in `sortByRelevance`; `groupKey` breadth) under "Next".

- [ ] **Step 2: Write docs/.last-agent**

One-line summary, current branch, and the HEAD commit hash:

```bash
git log --oneline -1
```

- [ ] **Step 3: Final verification**

```bash
python -m pytest && node --test tests/view/webview/main_js_contracts.test.js
```

Both green. Report the actual counts — do not claim a number you did not see.

- [ ] **Step 4: Commit**

```bash
git add docs/STATUS.md docs/.last-agent
git commit -m "docs: hand off cross-source search normalization

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Verification the tests cannot do

The defect was only visible in the rendered GUI, and Atlas's WebKitGTK window cannot be
driven from here. **The manual pass in Task 7 Step 1 is required before this is called done**
and is Vatteck's to run. Until then STATUS.md must say the fix is unverified in the GUI.
