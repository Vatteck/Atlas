# Tier 2 Power User Features Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Add five power-user features to the web UI — disk usage breakdown, orphan cleanup, package pinning/hold, export/import package manifests, and global keyboard shortcuts.

**Architecture:** All new Python bridge methods follow the same pattern as Tier 1: registered on `BauhApi`, return `{'status': 'ok', 'data': ...}` or `{'status': 'error', 'message': ...}`. Frontend consumes them via `pyApiCall()`. `fill_sizes()` is called per-view as a lazy enrichment pass, not on every list render. Package pinning maps directly to the existing `ignore_update()` / `revert_ignored_update()` abstract methods already implemented in Arch and AppImage gems. Orphan detection filters `read_installed` results by `pkg.orphan == True` (Arch only). Export/import serializes the installed package list to JSON with enough fields to reconstruct a machine.

**Tech Stack:** Python 3.14, pywebview ≥ 4.0, Vanilla HTML/CSS/JS, existing `GenericSoftwareManager`, `SoftwareManager` abstract API.

**Path Convention:** Python changes in `bauh/view/web/api.py`. New utility in `bauh/view/web/export.py`. Frontend assets in `bauh/view/web/{main.js,style.css,index.html}`.

---

## Task 1: Disk Usage Breakdown per Package and per Type

**Files:**
- Modify: `bauh/view/web/api.py`
- Modify: `bauh/view/web/main.js`
- Modify: `bauh/view/web/style.css`
- Modify: `bauh/view/web/index.html`

**Context:** `GenericSoftwareManager.fill_sizes(pkgs)` calls each gem's `fill_sizes` which populates `pkg.size` (bytes as `int`). `get_human_size_str(size)` in `bauh/commons/view_utils.py` returns human-readable strings. We call `fill_sizes` after `read_installed` returns, in a second pass, so package list loads fast then sizes stream in. The result is pushed to the frontend via a new `window.updatePackageSizes(sizeMap)` JS function.

**Step 1: Add `get_disk_usage` to `api.py`**

Add the following method to `BauhApi` in `bauh/view/web/api.py`:

```python
def get_disk_usage(self) -> dict:
    """
    Returns per-package sizes and a per-type breakdown summary.
    Calls fill_sizes on installed packages — can be slow, run only when user navigates to disk view.
    """
    try:
        self.logger.info("get_disk_usage called")
        from bauh.commons.view_utils import get_human_size_str
        result = self.manager.read_installed()
        pkgs = result.installed or []
        self.manager.fill_sizes(pkgs)

        pkg_sizes = []
        type_totals = {}  # pkg_type -> bytes
        for pkg in pkgs:
            pkg_id = str(id(pkg))
            with self._registry_lock:
                self.pkg_registry[pkg_id] = pkg
            size_bytes = pkg.size or 0
            try:
                pkg_type = pkg.get_type() or pkg.gem_name
            except Exception:
                pkg_type = pkg.gem_name
            type_totals[pkg_type] = type_totals.get(pkg_type, 0) + size_bytes
            pkg_sizes.append({
                'id': pkg_id,
                'name': pkg.name,
                'type': pkg_type,
                'size_bytes': size_bytes,
                'size_human': get_human_size_str(size_bytes) if size_bytes else 'Unknown',
            })

        # Sort largest first
        pkg_sizes.sort(key=lambda x: x['size_bytes'], reverse=True)

        type_summary = [
            {
                'type': t,
                'size_bytes': b,
                'size_human': get_human_size_str(b) if b else '0 B'
            }
            for t, b in sorted(type_totals.items(), key=lambda x: x[1], reverse=True)
        ]

        return {'status': 'ok', 'data': {'packages': pkg_sizes, 'by_type': type_summary}}
    except Exception as e:
        self.logger.error(f"Error computing disk usage: {e}")
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}
```

**Step 2: Add "Disk" sidebar nav item to `index.html`**

In the `<nav class="sidebar-nav">` block, after the `updates` button and before `activity`, add:

```html
<button class="nav-item" data-view="disk">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 8v4l3 3"></path></svg>
    Disk
</button>
```

**Step 3: Add disk view renderer to `main.js`**

Add `renderDiskView()` function after `renderActivityFeed`:

```js
async function renderDiskView() {
    packagesGrid.innerHTML = '';
    packagesGrid.style.display = 'block';
    loadingState.classList.remove('hidden');

    const data = await pyApiCall('get_disk_usage');
    loadingState.classList.add('hidden');

    if (!data) return;

    const { packages, by_type } = data;

    const totalBytes = by_type.reduce((sum, t) => sum + t.size_bytes, 0);
    const totalHuman = formatBytes(totalBytes);

    const container = document.createElement('div');
    container.className = 'disk-view';

    // Summary header
    container.innerHTML = `
        <div class="disk-summary">
            <h2 class="disk-total-label">Total Managed: <span class="disk-total-value">${totalHuman}</span></h2>
            <div class="disk-type-bars">
                ${by_type.map(t => {
                    const pct = totalBytes > 0 ? ((t.size_bytes / totalBytes) * 100).toFixed(1) : 0;
                    return `
                        <div class="disk-type-row">
                            <span class="tag ${t.type.toLowerCase()}">${t.type}</span>
                            <div class="disk-bar-track"><div class="disk-bar-fill tag-${t.type.toLowerCase()}" style="width:${pct}%"></div></div>
                            <span class="disk-type-size">${t.size_human}</span>
                            <span class="disk-type-pct">${pct}%</span>
                        </div>`;
                }).join('')}
            </div>
        </div>
        <div class="disk-pkg-list">
            ${packages.map(p => `
                <div class="disk-pkg-row">
                    <span class="disk-pkg-name">${p.name}</span>
                    <span class="tag ${p.type.toLowerCase()}">${p.type}</span>
                    <span class="disk-pkg-size">${p.size_human}</span>
                </div>`).join('')}
        </div>
    `;
    packagesGrid.appendChild(container);
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1000));
    return `${(bytes / Math.pow(1000, i)).toFixed(1)} ${units[i]}`;
}
```

**Step 4: Wire `disk` view in `fetchPackages` nav switch**

In `fetchPackages()`, in the view routing block, add alongside `activity`:

```js
} else if (currentView === 'disk') {
    loadingState.classList.add('hidden');
    renderDiskView();
    return;
}
```

**Step 5: Add CSS for disk view to `style.css`**

```css
/* Disk Usage View */
.disk-view { padding: 24px 32px; display: flex; flex-direction: column; gap: 24px; }
.disk-summary { background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: 24px; }
.disk-total-label { font-size: 14px; font-weight: 500; color: var(--text-secondary); margin-bottom: 20px; }
.disk-total-value { color: var(--text-primary); font-size: 28px; font-weight: 700; margin-left: 8px; }
.disk-type-bars { display: flex; flex-direction: column; gap: 12px; }
.disk-type-row { display: flex; align-items: center; gap: 12px; }
.disk-bar-track { flex: 1; height: 8px; background: var(--border-color); border-radius: 4px; overflow: hidden; }
.disk-bar-fill { height: 100%; border-radius: 4px; background: var(--accent-color); transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1); }
.disk-bar-fill.tag-aur { background: #1793d1; }
.disk-bar-fill.tag-flatpak { background: #4a86cf; }
.disk-bar-fill.tag-snap { background: #e95420; }
.disk-bar-fill.tag-appimage { background: #94a3b8; }
.disk-type-size { font-size: 13px; font-weight: 600; color: var(--text-primary); min-width: 80px; text-align: right; }
.disk-type-pct { font-size: 12px; color: var(--text-secondary); min-width: 42px; text-align: right; }
.disk-pkg-list { display: flex; flex-direction: column; gap: 6px; }
.disk-pkg-row { display: flex; align-items: center; gap: 12px; padding: 10px 16px; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: var(--radius-md); font-size: 13px; }
.disk-pkg-name { flex: 1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.disk-pkg-size { font-weight: 600; color: var(--text-primary); min-width: 80px; text-align: right; }
```

**Step 6: Commit**

```bash
git add bauh/view/web/api.py bauh/view/web/main.js bauh/view/web/style.css bauh/view/web/index.html
git commit -m "feat: add disk usage breakdown view"
```

---

## Task 2: Orphan Package Cleanup

**Files:**
- Modify: `bauh/view/web/api.py`
- Modify: `bauh/view/web/main.js`
- Modify: `bauh/view/web/index.html`

**Context:** `ArchPackage.orphan` is a `@property` (returns `bool`) in `bauh/gems/arch/model.py`. Orphan detection only applies to Arch packages — `pkg.gem_name == 'arch'`. We detect them by filtering `read_installed()`. Removal uses the existing `uninstall()` path with the terminal watcher. We expose a "Cleanup Orphans" button in the Updates view topbar that is only visible when orphans exist. No new sidebar nav needed.

**Step 1: Add `get_orphans` to `api.py`**

```python
def get_orphans(self) -> dict:
    """
    Returns all installed orphan packages (Arch only — packages with no remaining dependents).
    """
    try:
        self.logger.info("get_orphans called")
        result = self.manager.read_installed()
        orphans = []
        for pkg in (result.installed or []):
            if hasattr(pkg, 'orphan') and pkg.orphan:
                orphans.append(self._serialize_pkg(pkg))
        return {'status': 'ok', 'data': orphans}
    except Exception as e:
        self.logger.error(f"Error fetching orphans: {e}")
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}
```

**Step 2: Add "Orphan Cleanup" button to `index.html` topbar filters**

After the `#update-all-btn`, add:

```html
<button id="cleanup-orphans-btn" class="btn btn-danger hidden">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;">
        <polyline points="3 6 5 6 21 6"></polyline>
        <path d="M19 6l-1 14H6L5 6"></path>
        <path d="M10 11v6M14 11v6"></path>
    </svg>
    Cleanup Orphans
</button>
```

**Step 3: Wire orphan detection and cleanup in `main.js`**

After `updateAllBtn` wiring, add:

```js
const cleanupOrphansBtn = document.getElementById('cleanup-orphans-btn');

// Check for orphans when viewing installed packages
async function checkOrphans() {
    const orphans = await pyApiCall('get_orphans') || [];
    if (orphans.length > 0) {
        cleanupOrphansBtn.classList.remove('hidden');
        cleanupOrphansBtn.dataset.orphanIds = JSON.stringify(orphans.map(o => o.id));
        cleanupOrphansBtn.textContent = `Cleanup ${orphans.length} Orphan${orphans.length > 1 ? 's' : ''}`;
    } else {
        cleanupOrphansBtn.classList.add('hidden');
    }
}

cleanupOrphansBtn.addEventListener('click', async () => {
    const ids = JSON.parse(cleanupOrphansBtn.dataset.orphanIds || '[]');
    if (ids.length === 0) return;
    showToast('Orphan Cleanup', `Removing ${ids.length} orphaned package(s)...`, 'info');
    const result = await pyApiCall('batch_uninstall', ids);
    if (result && result.success) {
        showToast('Done', 'Orphaned packages removed', 'success');
        cleanupOrphansBtn.classList.add('hidden');
        fetchPackages();
    }
});
```

In `fetchPackages()`, after rendering installed packages, call `checkOrphans()` when `currentView === 'installed'`:

```js
if (currentView === 'installed' && !query) {
    checkOrphans();
}
```

**Step 4: Commit**

```bash
git add bauh/view/web/api.py bauh/view/web/main.js bauh/view/web/index.html
git commit -m "feat: add orphan package detection and cleanup"
```

---

## Task 3: Package Pinning / Update Hold

**Files:**
- Modify: `bauh/view/web/api.py`
- Modify: `bauh/view/web/main.js`
- Modify: `bauh/view/web/style.css`

**Context:** `SoftwareManager.ignore_update(pkg)` and `revert_ignored_update(pkg)` are already implemented in `ArchManager` and `AppImageManager`. The model has `pkg.supports_ignored_updates()` and `pkg.is_update_ignored()`. The `_serialize_pkg` method already exists — extend it to include `update_ignored` and `supports_pinning` fields. The pin/unpin toggle button appears on the package card in the **Installed** and **Updates** views only (not on uninstalled packages from suggestions).

**Step 1: Extend `_serialize_pkg` in `api.py`**

Add two fields to the returned dict inside `_serialize_pkg`:

```python
'update_ignored': pkg.is_update_ignored() if hasattr(pkg, 'is_update_ignored') else False,
'supports_pinning': pkg.supports_ignored_updates() if hasattr(pkg, 'supports_ignored_updates') else False,
```

**Step 2: Add `pin_update` and `unpin_update` to `api.py`**

```python
def pin_update(self, pkg_id: str) -> dict:
    """Prevents a package from appearing in / being processed by Update All."""
    pkg = self._get_pkg(pkg_id)
    if not pkg:
        return {'status': 'error', 'message': f'Unknown package id: {pkg_id}'}
    try:
        self.manager.ignore_update(pkg)
        self.logger.info(f"Pinned (update ignored): {pkg.name}")
        return {'status': 'ok', 'success': True}
    except Exception as e:
        self.logger.error(f"Error pinning {pkg.name}: {e}")
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}

def unpin_update(self, pkg_id: str) -> dict:
    """Allows a package to receive updates again."""
    pkg = self._get_pkg(pkg_id)
    if not pkg:
        return {'status': 'error', 'message': f'Unknown package id: {pkg_id}'}
    try:
        self.manager.revert_ignored_update(pkg)
        self.logger.info(f"Unpinned (update reverted): {pkg.name}")
        return {'status': 'ok', 'success': True}
    except Exception as e:
        self.logger.error(f"Error unpinning {pkg.name}: {e}")
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}
```

**Step 3: Add pin button to card renderer in `main.js`**

In `renderPackages()`, inside the card construction, add a pin button after `actionButton` when `pkg.installed && pkg.supports_pinning`:

```js
const pinButton = (pkg.installed && pkg.supports_pinning) ?
    `<button class="btn btn-pin ${pkg.update_ignored ? 'pinned' : ''} action-btn"
        data-action="${pkg.update_ignored ? 'unpin' : 'pin'}"
        data-id="${pkg.id}"
        title="${pkg.update_ignored ? 'Click to allow updates' : 'Click to hold (pin) this version'}">
        ${pkg.update_ignored ? '📌 Pinned' : '📌 Pin'}
    </button>` : '';
```

Add `pinButton` to card innerHTML alongside `actionButton`. Wire in the card's action button event listener:

```js
if (action === 'pin') {
    const res = await pyApiCall('pin_update', pid);
    if (res && res.success) { showToast('Pinned', `${pkg.name} will not be updated automatically`, 'info'); fetchPackages(); }
} else if (action === 'unpin') {
    const res = await pyApiCall('unpin_update', pid);
    if (res && res.success) { showToast('Unpinned', `${pkg.name} will receive updates again`, 'success'); fetchPackages(); }
}
```

**Step 4: Add CSS for pin button to `style.css`**

```css
.btn-pin {
    background: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    font-size: 12px;
    padding: 5px 10px;
}
.btn-pin:hover { background: var(--bg-surface-hover); color: var(--text-primary); }
.btn-pin.pinned { background: rgba(245, 158, 11, 0.1); border-color: var(--status-warning); color: var(--status-warning); }
.btn-pin.pinned:hover { background: var(--status-warning); color: white; }
```

**Step 5: Commit**

```bash
git add bauh/view/web/api.py bauh/view/web/main.js bauh/view/web/style.css
git commit -m "feat: add package pinning (update hold) support"
```

---

## Task 4: Export / Import Package Manifest

**Files:**
- New: `bauh/view/web/export.py`
- Modify: `bauh/view/web/api.py`
- Modify: `bauh/view/web/main.js`
- Modify: `bauh/view/web/index.html`

**Context:** Export serializes `read_installed()` to a JSON file. Import reads the file and calls `search()` + `install()` for each entry not already installed. The export file is written to `~/bauh-manifest.json` since pywebview running inside a sandbox cannot trigger browser file downloads. The path is returned so the UI can display it. Import path is hardcoded to the same location — user can move the file before importing.

**Step 1: Create `bauh/view/web/export.py`**

```python
import json
import os
import datetime
from typing import List

MANIFEST_PATH = os.path.expanduser('~/bauh-manifest.json')

def write_manifest(packages: List[dict]) -> str:
    """Writes the package manifest to ~/bauh-manifest.json. Returns the path."""
    manifest = {
        'created': datetime.datetime.now().isoformat(),
        'version': 1,
        'packages': packages
    }
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    return MANIFEST_PATH

def read_manifest() -> List[dict]:
    """Reads the manifest from ~/bauh-manifest.json. Returns list of package dicts."""
    if not os.path.exists(MANIFEST_PATH):
        raise FileNotFoundError(f"No manifest found at {MANIFEST_PATH}")
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('packages', [])
```

**Step 2: Add `export_packages` and `import_packages` to `api.py`**

```python
from bauh.view.web.export import write_manifest, read_manifest

def export_packages(self) -> dict:
    """Exports installed packages to ~/bauh-manifest.json."""
    try:
        self.logger.info("export_packages called")
        result = self.manager.read_installed()
        pkgs = result.installed or []
        serialized = [self._serialize_pkg(p) for p in pkgs]
        path = write_manifest(serialized)
        return {'status': 'ok', 'data': {'path': path, 'count': len(serialized)}}
    except Exception as e:
        self.logger.error(f"Error exporting packages: {e}")
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}

def import_packages(self) -> dict:
    """
    Reads ~/bauh-manifest.json and installs any packages not already present.
    Returns a summary of what was installed, skipped, or failed.
    """
    try:
        self.logger.info("import_packages called")
        manifest_pkgs = read_manifest()
        installed_res = self.manager.read_installed()
        installed_names = {p.name.lower() for p in (installed_res.installed or [])}

        to_install = [p for p in manifest_pkgs if p['name'].lower() not in installed_names]
        skipped = len(manifest_pkgs) - len(to_install)
        failed = []
        installed_count = 0

        if self.window:
            self.window.evaluate_js(f"terminalOpen('Importing {len(to_install)} packages from manifest...')")

        watcher = WebviewWatcher(self.logger, self.window)

        for entry in to_install:
            # Search for the package to get a live pkg object
            name = entry.get('name', '')
            pkg_type = entry.get('type', '').lower()
            search_res = self.manager.search(words=name)
            candidates = (search_res.installed or []) + (search_res.new or [])
            match = next(
                (p for p in candidates if p.name.lower() == name.lower()),
                None
            )
            if match:
                res = self.manager.install(match, root_password=None, disk_loader=None, handler=watcher)
                if res and res.success:
                    installed_count += 1
                    record_activity('install', match.name, match.get_type() or match.gem_name, True)
                else:
                    failed.append(name)
                    record_activity('install', name, pkg_type, False, 'import failed')
            else:
                failed.append(name)

        if self.window:
            self.window.evaluate_js(f"terminalSetDone(true)")

        return {
            'status': 'ok',
            'data': {
                'installed': installed_count,
                'skipped': skipped,
                'failed': failed
            }
        }
    except Exception as e:
        self.logger.error(f"Error importing packages: {e}")
        traceback.print_exc()
        if self.window:
            self.window.evaluate_js("terminalSetDone(false)")
        return {'status': 'error', 'message': str(e)}
```

**Step 3: Add Export/Import buttons to `index.html` sidebar footer**

In `<div class="sidebar-footer">`, alongside the theme toggle:

```html
<button id="export-btn" class="btn btn-outline" style="font-size:12px; width:100%; margin-bottom:8px;" title="Export installed packages to ~/bauh-manifest.json">⬆ Export</button>
<button id="import-btn" class="btn btn-outline" style="font-size:12px; width:100%;" title="Install packages from ~/bauh-manifest.json">⬇ Import</button>
```

**Step 4: Wire export/import in `main.js`**

```js
document.getElementById('export-btn').addEventListener('click', async () => {
    showToast('Exporting', 'Writing manifest...', 'info');
    const result = await pyApiCall('export_packages');
    if (result && result.count !== undefined) {
        showToast('Exported', `${result.count} packages saved to ${result.path}`, 'success');
    }
});

document.getElementById('import-btn').addEventListener('click', async () => {
    showToast('Importing', 'Reading ~/bauh-manifest.json and installing missing packages...', 'info');
    const result = await pyApiCall('import_packages');
    if (result) {
        const { installed, skipped, failed } = result;
        showToast('Import Complete',
            `Installed: ${installed} | Skipped (already present): ${skipped} | Failed: ${failed.length}`,
            failed.length > 0 ? 'error' : 'success');
    }
});
```

**Step 5: Commit**

```bash
git add bauh/view/web/export.py bauh/view/web/api.py bauh/view/web/main.js bauh/view/web/index.html
git commit -m "feat: add package export/import manifest support"
```

---

## Task 5: Global Keyboard Shortcuts

**Files:**
- Modify: `bauh/view/web/main.js`

**Context:** Pure JS, no Python changes. All shortcuts use `keydown` on `document` with guard for when the user is typing inside `#search-input`. Active view navigation mirrors the sidebar nav click.

**Step 1: Add keyboard shortcut handler to `main.js`**

Append the following at the end of `main.js`:

```js
// ─── Keyboard Shortcuts ───────────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    const tag = document.activeElement.tagName.toLowerCase();
    const inInput = tag === 'input' || tag === 'textarea' || tag === 'select';

    // / → Focus search
    if (e.key === '/' && !inInput) {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
        return;
    }

    // Escape → Clear search / close modal / close terminal / exit select mode
    if (e.key === 'Escape') {
        if (!detailModal.classList.contains('hidden')) {
            detailModal.classList.add('hidden');
            return;
        }
        if (!document.getElementById('terminal-panel').classList.contains('hidden') && !operationInProgress) {
            document.getElementById('terminal-panel').classList.add('hidden');
            document.getElementById('terminal-overlay').classList.add('hidden');
            return;
        }
        if (selectMode) {
            toggleSelectMode(false);
            return;
        }
        if (searchInput.value) {
            searchInput.value = '';
            fetchPackages();
            return;
        }
    }

    // Ctrl+U → Switch to Updates view
    if (e.ctrlKey && e.key === 'u') {
        e.preventDefault();
        activateView('updates');
        return;
    }

    // Ctrl+I → Switch to Installed view
    if (e.ctrlKey && e.key === 'i') {
        e.preventDefault();
        activateView('installed');
        return;
    }

    // Ctrl+H → Switch to Dashboard (Home)
    if (e.ctrlKey && e.key === 'h') {
        e.preventDefault();
        activateView('dashboard');
        return;
    }

    // Ctrl+A → Switch to Activity log
    if (e.ctrlKey && e.key === 'a' && !inInput) {
        e.preventDefault();
        activateView('activity');
        return;
    }

    // Ctrl+D → Switch to Disk usage view
    if (e.ctrlKey && e.key === 'd') {
        e.preventDefault();
        activateView('disk');
        return;
    }

    // Ctrl+Shift+U → Update All (only in updates view)
    if (e.ctrlKey && e.shiftKey && e.key === 'U') {
        e.preventDefault();
        if (!updateAllBtn.classList.contains('hidden')) {
            updateAllBtn.click();
        }
        return;
    }

    // Ctrl+E → Export
    if (e.ctrlKey && e.key === 'e') {
        e.preventDefault();
        document.getElementById('export-btn').click();
        return;
    }
});

// Helper to activate a view by name (mirrors nav item click)
function activateView(viewName) {
    navItems.forEach(n => n.classList.remove('active'));
    const target = document.querySelector(`.nav-item[data-view="${viewName}"]`);
    if (target) target.classList.add('active');
    currentView = viewName;
    searchInput.value = '';
    fetchPackages();
}
```

**Step 2: Add keyboard shortcut help tooltip to sidebar footer (optional polish)**

In `index.html`, add a small `?` icon button next to the theme toggle that shows a toast with shortcut list:

```html
<button id="shortcuts-help-btn" class="icon-button" aria-label="Keyboard shortcuts" title="Show keyboard shortcuts">?</button>
```

Wire in `main.js`:

```js
document.getElementById('shortcuts-help-btn').addEventListener('click', () => {
    showToast('Keyboard Shortcuts',
        '/ Search  •  Esc Clear/Close  •  Ctrl+H Home  •  Ctrl+I Installed  •  Ctrl+U Updates  •  Ctrl+A Activity  •  Ctrl+D Disk  •  Ctrl+Shift+U Update All  •  Ctrl+E Export',
        'info');
});
```

**Step 3: Commit**

```bash
git add bauh/view/web/main.js bauh/view/web/index.html
git commit -m "feat: add global keyboard shortcuts and shortcut help"
```

---

## Verification Plan

### Run the app

```bash
cd /home/vatteck/git/bauh
source venv/bin/activate
python -m bauh.app --logs
```

Expected: No Python exceptions on startup. Window opens. All five new features should be accessible.

### Manual Checks

1. **Disk view** — Click "Disk" in sidebar. Should show per-type bar chart and per-package list sorted largest-first. Verify sizes are non-zero for at least Arch and Flatpak packages.
2. **Orphan cleanup** — Switch to Installed. If any Arch orphans exist, "Cleanup N Orphans" button should appear. Click it, verify terminal opens and batch uninstall runs.
3. **Package pinning** — In Installed view, any Arch or AppImage card should show a "📌 Pin" button. Pin one. Verify it shows "📌 Pinned" on reload. Verify it no longer appears in Updates view. Unpin and verify it's back.
4. **Export** — Click "⬆ Export" in sidebar footer. Verify `~/bauh-manifest.json` is created with correct structure. Check `count` matches installed list size.
5. **Import** — Move or copy the manifest to a clean test. Click "⬇ Import". Verify terminal opens and already-installed packages are skipped.
6. **Keyboard shortcuts** — Press `/` to focus search. Press `Ctrl+U` to switch to Updates. Press `Ctrl+I` for Installed. Press `Ctrl+H` for Dashboard. Press `Escape` to clear search / close modal / exit select mode. Click `?` to verify shortcut toast.
