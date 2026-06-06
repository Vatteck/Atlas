# Security + Webview Loading Pass Implementation Plan

> **For Hermes:** Use focused TDD/contract tests before touching production code. Keep this pass narrow: fix verified security footguns and duplicated startup I/O only.

**Goal:** Harden Atlas's webview HTML helper path and make startup/dashboard loading snappier by removing duplicate expensive calls.

**Architecture:** Atlas's frontend is a single pywebview/WebKitGTK page backed by `AtlasApi`. This pass keeps the pure-Python + plain-JS architecture, adds no dependencies, and uses the existing Node VM contract harness plus Python unit tests. Optimization is limited to measured/observable redundant I/O on startup: share the in-flight Updates fetch used by the dashboard and sidebar badge instead of firing `get_updates` twice.

**Tech Stack:** Python stdlib (`html.escape`, `urllib.parse`), plain JavaScript, pytest, Node VM contract tests.

---

## Findings driving this pass

1. **Security:** `atlas.commons.html.bold()` and `link()` interpolate raw values into HTML strings. Those strings flow into webview modal bodies/statuses; package names, paths, URLs, or translated values containing `<script>`, event attributes, or quoted attributes can become injected markup.
2. **Security:** `main.js` still intentionally renders a serialized `TextComponent` as HTML (`renderConfirmComponent`), so helper-generated markup must be escaped at the Python helper boundary rather than assuming every caller remembered to escape.
3. **Loading:** startup currently runs `fetchPackages()` on `pywebviewready`; the dashboard path calls `renderAttentionCenter()`, which calls `get_updates`, then startup immediately calls `refreshUpdatesBadge()`, which calls `get_updates` again. `get_updates` is explicitly the expensive `read_installed` path; duplicated calls make first paint and first idle worse.

---

## Task 1: Add Python HTML helper security tests

**Objective:** Prove `bold()` escapes text content and `link()` escapes URL attributes/text while preserving normal helper markup.

**Files:**
- Modify: `tests/common/test_html.py` (create if missing)
- Modify after RED: `atlas/commons/html.py`

**Steps:**
1. Create tests for:
   - `bold('<img src=x onerror=alert(1)>')` returns a `<span ...>` whose contents are escaped.
   - `link('https://example.invalid/?q=" onclick="x')` escapes both href attribute and visible text.
   - `strip_html('<b>ok</b>')` still returns `ok`.
2. Run `python -m pytest tests/common/test_html.py -q` and verify RED.
3. Implement with `html.escape(..., quote=True)`.
4. Run focused test again and verify GREEN.

## Task 2: Share in-flight Updates fetches in the webview

**Objective:** Make `renderAttentionCenter()` and `refreshUpdatesBadge()` reuse the same cached/in-flight `get_updates('all')` request.

**Files:**
- Modify: `tests/view/webview/main_js_contracts.test.js`
- Modify after RED: `atlas/view/webview/main.js`

**Steps:**
1. Add a Node VM contract test where `get_updates` counts calls and resolves from a controlled promise.
2. Trigger `renderAttentionCenter()` and `refreshUpdatesBadge()` before the updates promise resolves.
3. Assert only one backend `get_updates` call happens, both consumers update state/UI after the promise resolves, and the updates cache is populated.
4. Verify RED with `python -m pytest tests/view/webview/test_main_js.py -q`.
5. Implement a small helper such as `getUpdatesCached()` with a module-level `updatesInFlight` promise and the existing `packageCache` key.
6. Use it from both `refreshUpdatesBadge()` and `renderAttentionCenter()`.
7. Verify GREEN with the same focused test.

## Task 3: Run focused security/static checks

**Objective:** Confirm no obvious shell/eval/secret regressions were introduced and capture remaining non-blocking findings.

**Files:**
- No production edits expected.

**Commands:**
- `python -m pytest tests/common/test_html.py tests/view/webview/test_main_js.py -q`
- `python -m pytest tests/view/webview tests/common -q`
- Security grep over changed diff for hardcoded secrets, `shell=True`, `os.system`, `eval`, `exec`, and `pickle.loads`.

## Task 4: Full verification and handoff

**Objective:** Prove the pass does not regress Atlas and update the live baton.

**Files:**
- Modify: `docs/STATUS.md`

**Commands:**
- `python -m pytest -q`
- `git diff --check`
- `git status --short --branch`

**STATUS update:** Add a concise Done entry with exact tests and remaining GUI-eyeball note if any.
