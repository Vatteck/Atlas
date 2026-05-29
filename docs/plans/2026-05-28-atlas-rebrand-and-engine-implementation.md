# Atlas Rebranding and Engine Modernization Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Purge the legacy Qt5 codebase, rebrand the entire project to "Atlas" under the `atlaspm` / `atlas-pm` namespaces, migrate config and cache directories, and refactor the background engine for lazy initialization and high-performance concurrency.

**Architecture:** Purge all legacy Qt files first. Rename the global root package from `bauh` to `atlas` and execute a global regex replacement on all module imports. Migrate configuration and cache directory constants from `bauh` to `atlaspm`. Modify `GenericSoftwareManager` and `app.py`/`api.py` to lazy-initialize backend gems and leverage thread-pool executor logic to eliminate UI thread blocks.

**Tech Stack:** Python 3.14, pywebview >= 4.0, Vanilla HTML/CSS/JS.

---

### Task 1: Purge Legacy Qt5 Codebase

**Files:**
- Delete: `bauh/view/qt/`
- Delete: `bauh/view/resources/style/`
- Delete: `tests/view/qt/`

**Step 1: Verify test suite before directory purge**

Run: `./venv/bin/python -m unittest discover -s tests`
Expected: 162 tests pass.

**Step 2: Delete legacy directories**

Run: `rm -rf bauh/view/qt/ bauh/view/resources/style/ tests/view/qt/`
Expected: Directories are fully removed.

**Step 3: Run test suite to verify no backend impact**

Run: `./venv/bin/python -m unittest discover -s tests`
Expected: All non-Qt backend tests (162 or slightly less without Qt tests) pass perfectly.

**Step 4: Commit**

```bash
git add -A
git commit -m "cleanup: purge legacy Qt5 GUI directories and resources"
```

---

### Task 2: Global Renaming to Atlas Namespace

**Files:**
- Rename: `bauh/` -> `atlas/`
- Modify: All python imports inside `atlas/` and `tests/`
- Rename: `atlas/view/web/` -> `atlas/view/webview/`

**Step 1: Rename the root packages**

Run:
```bash
mv bauh/ atlas/
mv atlas/view/web/ atlas/view/webview/
```
Expected: Directories renamed.

**Step 2: Perform global imports search and replace**

Find and replace all python module import strings across all `.py` files in `atlas/` and `tests/`:
- `import bauh` -> `import atlas`
- `from bauh` -> `from atlas`
- `bauh.` -> `atlas.` (in python modules and setups)

Also, update `setup.py` and `pyproject.toml` to replace `bauh` metadata references with `atlas`.

**Step 3: Run the tests to verify the renamed namespace**

Run: `./venv/bin/python -m unittest discover -s tests`
Expected: All tests pass under the new `atlas` import namespace.

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: globally rebrand and rename package namespace to atlas"
```

---

### Task 3: System Environment Refactoring (Config & Caches)

**Files:**
- Modify: `atlas/commons/constants.py` (or where config/cache paths are declared)
- Modify: `atlas/view/webview/api.py`

**Step 1: Locate and update environment constants**

Find path configurations (usually declared as `~/.config/bauh`, `~/.cache/bauh`, `/tmp/bauh@$USER`).
Update them to:
- Configuration: `~/.config/atlaspm`
- Cache: `~/.cache/atlaspm`
- Temp files: `/tmp/atlaspm@$USER`
- System-wide cache: `/var/cache/atlaspm`

**Step 2: Update UI static assets to use new brand name**

- Modify `atlas/view/webview/index.html` to change page title, headers, and footer credits from "bauh" to "Atlas".
- Update static strings or log files inside `atlas/view/webview/main.js`.

**Step 3: Run tests to verify path migrations**

Run: `./venv/bin/python -m unittest discover -s tests`
Expected: All tests pass cleanly.

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: migrate system paths to atlaspm and update UI text branding"
```

---

### Task 4: Concurrency and Lazy Gem Initialization

**Files:**
- Modify: `atlas/view/core/controller.py` (or the generic software manager class)
- Modify: `atlas/view/webview/api.py`
- Modify: `atlas/app.py`

**Step 1: Write unit test validating lazy loading of gems**

Add test to `tests/view/webview/test_api.py` verifying that gems are only initialized when their respective packages or categories are queried.

**Step 2: Implement on-demand lazy initialization**

- Refactor `GenericSoftwareManager.prepare()` to avoid eagerly loading backends.
- Load only the requested backend gem dynamically when query operations (`get_installed`, `get_updates`, `get_suggestions`) are executed for a specific packaging technology.
- In `api.py`, wrap blocking calls inside a `concurrent.futures.ThreadPoolExecutor` pool rather than custom `threading.Thread` instances to cleanly manage concurrency and avoid GUI thread lockups.

**Step 3: Run tests to verify lazy loading passes**

Run: `./venv/bin/python -m unittest discover -s tests`
Expected: All tests pass, including the new lazy loading validations.

**Step 4: Commit**

```bash
git add -A
git commit -m "perf: implement lazy gem initialization and threadpool concurrency in AtlasApi"
```
