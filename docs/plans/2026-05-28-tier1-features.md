# Tier 1 Features Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Wire real package manager backends and build all six Tier 1 UI features (real-time terminal output, progress indicators, package detail view, batch operations, Update All, and activity log) so bauh can serve as a primary daily-use package manager.

**Architecture:** A `WebviewProcessWatcher` class bridges the existing `ProcessWatcher` interface to the pywebview JS API via `window.evaluate_js()`, allowing all existing gem backends (Arch/AUR, Flatpak, Snap, AppImage, Web) to stream output, progress, and status to the frontend without modification. `BauhApi` (the pywebview JS bridge) stores serialized `SoftwarePackage` objects in a server-side registry keyed by opaque ID strings, so the frontend only handles plain JSON and never holds Python objects. An activity log is persisted to `~/.cache/bauh/activity.jsonl`.

**Tech Stack:** Python 3.14, pywebview ≥ 4.0, Vanilla HTML/CSS/JS (no build step), existing `GenericSoftwareManager` + gem backends unchanged.

**Path Convention:** All Python changes are inside `bauh/view/web/`. Frontend assets are `bauh/view/web/index.html`, `style.css`, `main.js`. New Python files are `bauh/view/web/api.py` (modify in place), `bauh/view/web/watcher.py` (new), `bauh/view/web/activity_log.py` (new).

---

## Task 1: Wire Real Backends — Search, Installed, Updates, Suggestions

**Files:**
- Modify: `bauh/view/web/api.py`
- New: `bauh/view/web/watcher.py`

**Context:** `BauhApi` currently returns hardcoded mock lists. `GenericSoftwareManager` is already initialized and passed to `BauhApi.__init__` in `app.py`. The manager's methods block on the calling thread (they use internal `Thread` objects internally), so all `BauhApi` methods must run manager calls in a background thread to avoid freezing the pywebview GTK event loop. pywebview's `js_api` methods **can** return values synchronously — pywebview serializes the return value to JSON and resolves the JS Promise on the main thread. However, long-running calls (>200ms) must be dispatched to a thread and use `window.evaluate_js()` to push results back, otherwise the webview freezes.

The manager stores deserialized `SoftwarePackage` subclass instances. These cannot be serialized to JSON directly. A `pkg_registry` dict (`{str_id -> SoftwarePackage}`) in `BauhApi` maps opaque IDs to packages so the frontend can reference them in install/uninstall calls.

**Step 1: Write `bauh/view/web/watcher.py`**

Create a minimal `ProcessWatcher` implementation that queues output lines for later streaming. Full streaming is implemented in Task 2; here we just need a no-op watcher so the manager calls don't crash.

```python
# bauh/view/web/watcher.py
import logging
from typing import Optional, List, Tuple
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MessageType, ViewComponent


class WebviewWatcher(ProcessWatcher):
    """Minimal ProcessWatcher for Task 1. Output is collected but not streamed yet."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._output_lines: List[str] = []
        self._stop = False

    def print(self, msg: str):
        if msg:
            self._output_lines.append(msg)
            self.logger.debug(f'[watcher] {msg}')

    def change_status(self, msg: str):
        self.logger.info(f'[status] {msg}')

    def change_substatus(self, msg: str):
        self.logger.info(f'[substatus] {msg}')

    def change_progress(self, val: int):
        self.logger.info(f'[progress] {val}%')

    def should_stop(self) -> bool:
        return self._stop

    def request_root_password(self) -> Tuple[bool, str]:
        return False, ''

    def request_confirmation(self, title: str, body: Optional[str], **kwargs) -> bool:
        # Auto-confirm for now; Task 5 will wire up a real JS confirmation dialog
        return True

    def show_message(self, title: str, body: str, type_: MessageType = MessageType.INFO):
        self.logger.info(f'[message] {title}: {body}')
```

**Step 2: Rewrite `bauh/view/web/api.py`**

Replace all mock methods. Key design rules:
- All manager calls run in a `threading.Thread` because they block.
- Return value pattern: `{'status': 'ok', 'data': [...]}` or `{'status': 'error', 'message': str}`.
- `_serialize_pkg(pkg)` converts a `SoftwarePackage` instance to a plain dict the frontend can render.
- All returned packages are registered in `self.pkg_registry` before serialization.

```python
# bauh/view/web/api.py
import logging
import threading
import traceback
from typing import List, Optional

from bauh.view.core.controller import GenericSoftwareManager
from bauh.view.web.watcher import WebviewWatcher


class BauhApi:

    def __init__(self, manager: GenericSoftwareManager, logger: logging.Logger):
        self.manager = manager
        self.logger = logger
        self.pkg_registry = {}  # opaque_id -> SoftwarePackage
        self._registry_lock = threading.Lock()
        # Kick off manager.prepare() in background so gems are ready
        self._prepare_thread = threading.Thread(
            target=self._prepare_manager, daemon=True)
        self._prepare_thread.start()

    def _prepare_manager(self):
        try:
            self.logger.info('Preparing manager backends...')
            self.manager.prepare(task_manager=None, root_password=None, internet_available=None)
            self.logger.info('Manager backends ready.')
        except Exception:
            traceback.print_exc()

    def _serialize_pkg(self, pkg) -> dict:
        pkg_id = str(id(pkg))
        with self._registry_lock:
            self.pkg_registry[pkg_id] = pkg
        return {
            'id': pkg_id,
            'name': pkg.name or '',
            'description': pkg.description or '',
            'version': pkg.version or '',
            'latest_version': pkg.latest_version or '',
            'type': pkg.get_type() if hasattr(pkg, 'get_type') else pkg.gem_name,
            'installed': bool(pkg.installed),
            'update_available': bool(pkg.update),
            'icon_url': pkg.icon_url or '',
            'publisher': pkg.get_publisher() if hasattr(pkg, 'get_publisher') else '',
            'size': pkg.size,
            'categories': list(pkg.categories) if pkg.categories else [],
            'can_be_run': pkg.can_be_run() if hasattr(pkg, 'can_be_run') else False,
            'can_be_downgraded': pkg.can_be_downgraded() if hasattr(pkg, 'can_be_downgraded') else False,
            'has_info': pkg.has_info() if hasattr(pkg, 'has_info') else False,
            'has_history': pkg.has_history() if hasattr(pkg, 'has_history') else False,
        }

    def _get_pkg(self, pkg_id: str):
        with self._registry_lock:
            return self.pkg_registry.get(pkg_id)

    def get_suggestions(self, pkg_type: str = 'all') -> dict:
        try:
            self.logger.info('get_suggestions called')
            suggestions = self.manager.list_suggestions(limit=20, filter_installed=False)
            pkgs = [s.package for s in (suggestions or [])]
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_installed(self, pkg_type: str = 'all') -> dict:
        try:
            self.logger.info('get_installed called')
            result = self.manager.read_installed()
            pkgs = result.installed or []
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_updates(self, pkg_type: str = 'all') -> dict:
        try:
            self.logger.info('get_updates called')
            updates = self.manager.list_updates()
            # list_updates returns PackageUpdate (lightweight), not SoftwarePackage
            # We need full packages: do read_installed and filter by update=True
            result = self.manager.read_installed()
            pkgs = [p for p in (result.installed or []) if p.update]
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def search(self, query: str, pkg_type: str = 'all') -> dict:
        try:
            self.logger.info(f'search called: {query}')
            result = self.manager.search(words=query)
            pkgs = (result.installed or []) + (result.new or [])
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def install(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f'Unknown package id: {pkg_id}'}
        try:
            watcher = WebviewWatcher(self.logger)
            result = self.manager.install(pkg, root_password=None, disk_loader=None, handler=watcher)
            return {'status': 'ok', 'success': result.success if result else False}
        except Exception as e:
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def uninstall(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f'Unknown package id: {pkg_id}'}
        try:
            watcher = WebviewWatcher(self.logger)
            result = self.manager.uninstall(pkg, root_password=None, handler=watcher)
            return {'status': 'ok', 'success': result.success if result else False}
        except Exception as e:
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def update(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f'Unknown package id: {pkg_id}'}
        try:
            watcher = WebviewWatcher(self.logger)
            reqs = self.manager.get_upgrade_requirements([pkg], root_password=None, watcher=watcher)
            success = self.manager.upgrade(reqs, root_password=None, handler=watcher)
            return {'status': 'ok', 'success': bool(success)}
        except Exception as e:
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_info(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f'Unknown package id: {pkg_id}'}
        try:
            info = self.manager.get_info(pkg)
            return {'status': 'ok', 'data': info or {}}
        except Exception as e:
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}
```

**Step 3: Update `main.js` to handle new response envelope**

The frontend currently expects raw lists. Update `pyApiCall` to unwrap `{status, data}`:

```javascript
async function pyApiCall(methodName, ...args) {
    if (window.pywebview && window.pywebview.api) {
        try {
            const response = await window.pywebview.api[methodName](...args);
            if (response && response.status === 'error') {
                showToast('Error', response.message, 'error');
                return null;
            }
            // Unwrap data envelope; fall back to raw response for non-envelope calls
            return (response && 'data' in response) ? response.data : response;
        } catch (error) {
            console.error(`Error calling ${methodName}:`, error);
            showToast('Error', `Backend error: ${error}`, 'error');
            return null;
        }
    } else {
        return mockApi[methodName](...args);
    }
}
```

**Step 4: Smoke test — run app, verify Installed tab shows real packages**

```bash
cd /home/vatteck/git/bauh
source venv/bin/activate
python -m bauh.app --logs
```

Expected: App opens. Clicking "Installed" shows real system packages (AUR/Flatpak/Snap entries). Logs show `get_installed called` and gem timings. No Python traceback in terminal.

**Step 5: Commit**

```bash
git add bauh/view/web/api.py bauh/view/web/watcher.py bauh/view/web/main.js
git commit -m "feat: wire real GenericSoftwareManager backends to web UI"
```

---

## Task 2: Real-Time Terminal Output Panel

**Files:**
- Modify: `bauh/view/web/watcher.py`
- Modify: `bauh/view/web/api.py`
- Modify: `bauh/view/web/index.html`
- Modify: `bauh/view/web/style.css`
- Modify: `bauh/view/web/main.js`

**Context:** pywebview exposes `window.evaluate_js(js_string)` on the `webview.Window` object. This can be called from any Python thread to push data to the frontend. `BauhApi` needs a reference to the `webview.Window` instance to call `evaluate_js`. The window is created in `app.py` — pass it into `BauhApi` after creation via a `set_window(window)` method called inside the `pywebviewready` handler (or just pass it at construction time using `webview.start()`'s `func` parameter — pass as `started` callback). The cleanest approach: call `api.set_window(window)` from `app.py` after `webview.create_window()`.

`WebviewWatcher.print()` will call `window.evaluate_js("terminalAppend(" + json.dumps(msg) + ")")` directly.

**Step 1: Add `set_window` to `BauhApi` and pass window in `app.py`**

In `bauh/view/web/api.py`, add:
```python
def set_window(self, window):
    self.window = window
```

In `bauh/app.py`, after `window = webview.create_window(...)`, add:
```python
api.set_window(window)
```

**Step 2: Upgrade `WebviewWatcher` to stream via `evaluate_js`**

```python
# bauh/view/web/watcher.py (updated)
import json
import logging
from typing import Optional, Tuple
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MessageType


class WebviewWatcher(ProcessWatcher):

    def __init__(self, logger: logging.Logger, window=None, op_id: str = ''):
        self.logger = logger
        self.window = window
        self.op_id = op_id
        self._stop = False

    def _push(self, js: str):
        if self.window:
            try:
                self.window.evaluate_js(js)
            except Exception:
                pass  # window may be closing

    def print(self, msg: str):
        if msg:
            self.logger.debug(f'[watcher] {msg}')
            escaped = json.dumps(msg)
            self._push(f'terminalAppend({escaped})')

    def change_status(self, msg: str):
        if msg:
            escaped = json.dumps(msg)
            self._push(f'terminalSetStatus({escaped})')

    def change_substatus(self, msg: str):
        if msg:
            escaped = json.dumps(msg)
            self._push(f'terminalSetSubstatus({escaped})')

    def change_progress(self, val: int):
        self._push(f'terminalSetProgress({int(val)})')

    def should_stop(self) -> bool:
        return self._stop

    def request_root_password(self) -> Tuple[bool, str]:
        return False, ''

    def request_confirmation(self, title: str, body: Optional[str], **kwargs) -> bool:
        return True

    def show_message(self, title: str, body: str, type_: MessageType = MessageType.INFO):
        escaped_title = json.dumps(title)
        escaped_body = json.dumps(body)
        level = 'error' if type_ == MessageType.ERROR else 'info'
        self._push(f"showToast({escaped_title}, {escaped_body}, '{level}')")
```

**Step 3: Wire watcher into install/uninstall/update in `BauhApi`**

Update all three operation methods to construct `WebviewWatcher(self.logger, self.window, pkg_id)` and call `terminalOpen()` before the operation starts:

```python
def install(self, pkg_id: str) -> dict:
    pkg = self._get_pkg(pkg_id)
    if not pkg:
        return {'status': 'error', 'message': f'Unknown package id: {pkg_id}'}
    try:
        if hasattr(self, 'window') and self.window:
            self.window.evaluate_js(f"terminalOpen('Installing {pkg.name}')")
        watcher = WebviewWatcher(self.logger, getattr(self, 'window', None))
        result = self.manager.install(pkg, root_password=None, disk_loader=None, handler=watcher)
        success = result.success if result else False
        if hasattr(self, 'window') and self.window:
            self.window.evaluate_js(f"terminalSetDone({str(success).lower()})")
        return {'status': 'ok', 'success': success}
    except Exception as e:
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}
```

Apply the same pattern to `uninstall()` and `update()`.

**Step 4: Add terminal panel to `index.html`**

Add before the closing `</body>` tag:

```html
<!-- Terminal Slide-out Panel -->
<div id="terminal-panel" class="terminal-panel hidden">
    <div class="terminal-header">
        <div class="terminal-header-left">
            <span class="terminal-title" id="terminal-title">Operation</span>
            <span class="terminal-status" id="terminal-status"></span>
        </div>
        <button class="terminal-close" id="terminal-close" aria-label="Close terminal">✕</button>
    </div>
    <div class="terminal-progress-bar">
        <div class="terminal-progress-fill" id="terminal-progress-fill" style="width:0%"></div>
    </div>
    <div class="terminal-substatus" id="terminal-substatus"></div>
    <div class="terminal-output" id="terminal-output"></div>
    <div class="terminal-footer">
        <span id="terminal-done-msg" class="hidden"></span>
    </div>
</div>
<div id="terminal-overlay" class="terminal-overlay hidden"></div>
```

**Step 5: Add terminal CSS to `style.css`**

```css
/* Terminal Panel */
.terminal-panel {
    position: fixed;
    top: 0;
    right: 0;
    width: 480px;
    height: 100vh;
    background: var(--surface);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    z-index: 200;
    transform: translateX(100%);
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: -8px 0 32px rgba(0,0,0,0.4);
}
.terminal-panel:not(.hidden) {
    transform: translateX(0);
}
.terminal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.3);
    z-index: 199;
}
.terminal-overlay:not(.hidden) { display: block; }
.terminal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
}
.terminal-title { font-weight: 600; font-size: 14px; }
.terminal-status { font-size: 12px; color: var(--text-secondary); margin-left: 8px; }
.terminal-close {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 18px;
    padding: 4px 8px;
    border-radius: 4px;
    transition: background 0.15s;
}
.terminal-close:hover { background: var(--surface-hover); color: var(--text-primary); }
.terminal-progress-bar {
    height: 3px;
    background: var(--border);
    flex-shrink: 0;
}
.terminal-progress-fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s ease;
}
.terminal-substatus {
    font-size: 11px;
    color: var(--text-secondary);
    padding: 6px 20px;
    min-height: 24px;
    flex-shrink: 0;
}
.terminal-output {
    flex: 1;
    overflow-y: auto;
    padding: 12px 20px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    line-height: 1.6;
    color: #a8ff78;
    background: #0d1117;
}
.terminal-output .line { display: block; word-break: break-all; }
.terminal-footer {
    padding: 12px 20px;
    border-top: 1px solid var(--border);
    flex-shrink: 0;
    min-height: 44px;
}
.terminal-done-success { color: var(--success); font-size: 13px; font-weight: 600; }
.terminal-done-error { color: var(--error); font-size: 13px; font-weight: 600; }
```

**Step 6: Add terminal JS functions to `main.js`**

```javascript
// Terminal Panel
const terminalPanel = document.getElementById('terminal-panel');
const terminalOverlay = document.getElementById('terminal-overlay');
const terminalOutput = document.getElementById('terminal-output');
const terminalTitle = document.getElementById('terminal-title');
const terminalStatus = document.getElementById('terminal-status');
const terminalSubstatus = document.getElementById('terminal-substatus');
const terminalProgressFill = document.getElementById('terminal-progress-fill');
const terminalDoneMsg = document.getElementById('terminal-done-msg');
const terminalCloseBtn = document.getElementById('terminal-close');

window.terminalOpen = function(title) {
    terminalTitle.textContent = title || 'Operation';
    terminalOutput.innerHTML = '';
    terminalStatus.textContent = '';
    terminalSubstatus.textContent = '';
    terminalProgressFill.style.width = '0%';
    terminalDoneMsg.className = 'hidden';
    terminalPanel.classList.remove('hidden');
    terminalOverlay.classList.remove('hidden');
};

window.terminalAppend = function(line) {
    const el = document.createElement('span');
    el.className = 'line';
    el.textContent = line;
    terminalOutput.appendChild(el);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
};

window.terminalSetStatus = function(msg) {
    terminalStatus.textContent = msg;
};

window.terminalSetSubstatus = function(msg) {
    terminalSubstatus.textContent = msg;
};

window.terminalSetProgress = function(val) {
    terminalProgressFill.style.width = Math.min(100, Math.max(0, val)) + '%';
};

window.terminalSetDone = function(success) {
    terminalProgressFill.style.width = '100%';
    terminalDoneMsg.textContent = success ? '✓ Completed successfully' : '✗ Operation failed';
    terminalDoneMsg.className = success ? 'terminal-done-success' : 'terminal-done-error';
};

terminalCloseBtn.addEventListener('click', () => {
    terminalPanel.classList.add('hidden');
    terminalOverlay.classList.add('hidden');
    fetchPackages(); // refresh view after operation
});
terminalOverlay.addEventListener('click', () => {
    terminalPanel.classList.add('hidden');
    terminalOverlay.classList.add('hidden');
    fetchPackages();
});
```

**Step 7: Smoke test terminal output**

Run app, trigger an install or uninstall. Expected: slide-out panel appears from the right with a green monospace terminal showing live output from the package manager. Progress bar fills. "✓ Completed" or "✗ Failed" appears in footer. Dismissing panel refreshes the package list.

**Step 8: Commit**

```bash
git add bauh/view/web/watcher.py bauh/view/web/api.py bauh/view/web/index.html \
        bauh/view/web/style.css bauh/view/web/main.js bauh/app.py
git commit -m "feat: real-time terminal output panel with progress and status streaming"
```

---

## Task 3: Progress Indicators on Package Cards

**Files:**
- Modify: `bauh/view/web/main.js`
- Modify: `bauh/view/web/style.css`

**Context:** While an operation is running, the package card that triggered it should visually indicate it's busy (spinner on the action button, button disabled). This is purely frontend — no backend changes needed. The `installApp`, `uninstallApp`, `updateApp` handlers in `main.js` already exist; they need to set a loading state on the triggering button before the `await` and restore it after.

**Step 1: Add loading state CSS**

```css
.btn.loading {
    opacity: 0.6;
    cursor: not-allowed;
    pointer-events: none;
    position: relative;
}
.btn.loading::after {
    content: '';
    display: inline-block;
    width: 12px;
    height: 12px;
    margin-left: 8px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

**Step 2: Update action handlers to manage button loading state**

Replace the existing `installApp`, `uninstallApp`, `updateApp` window functions with versions that accept the triggering button element and toggle its loading state:

```javascript
// In renderPackages(), update button onclick to pass `this`:
`<button class="btn btn-primary" onclick="installApp('${pkg.id}', this)">Install</button>`
`<button class="btn btn-danger" onclick="uninstallApp('${pkg.id}', this)">Uninstall</button>`
`<button class="btn btn-primary" onclick="updateApp('${pkg.id}', this)">Update</button>`

window.installApp = async (id, btn) => {
    if (btn) { btn.classList.add('loading'); btn.disabled = true; }
    showToast('Installing', 'Installation started', 'info');
    const result = await pyApiCall('install', id);
    if (btn) { btn.classList.remove('loading'); btn.disabled = false; }
    if (result && result.success) {
        showToast('Success', 'Application installed', 'success');
        fetchPackages();
    } else {
        showToast('Error', result ? result.error : 'Installation failed', 'error');
    }
};
// Same pattern for uninstallApp and updateApp
```

**Step 3: Smoke test**

Click Install/Uninstall/Update. Button immediately shows spinner and is disabled. Terminal panel opens. After operation completes, button returns to normal and list refreshes.

**Step 4: Commit**

```bash
git add bauh/view/web/main.js bauh/view/web/style.css
git commit -m "feat: loading state spinners on package action buttons"
```

---

## Task 4: Package Detail View

**Files:**
- Modify: `bauh/view/web/index.html`
- Modify: `bauh/view/web/style.css`
- Modify: `bauh/view/web/main.js`

**Context:** Clicking a package card (not the action button) opens a detail modal/drawer showing full package info from `BauhApi.get_info()`. The `get_info` method already exists from Task 1; it calls `GenericSoftwareManager.get_info(pkg)` which returns a raw `dict` of attributes. Structure varies by gem — Flatpak returns different keys than AUR. The detail view should render all keys as a generic key-value table, plus the fixed fields (`name`, `version`, `description`, `publisher`, `size`, `categories`) from the serialized package.

**Step 1: Add detail modal HTML to `index.html`**

```html
<!-- Package Detail Modal -->
<div id="detail-modal" class="modal hidden" role="dialog" aria-modal="true">
    <div class="modal-backdrop"></div>
    <div class="modal-content">
        <div class="modal-header">
            <div class="modal-header-left">
                <img id="detail-icon" class="modal-icon" src="" alt="">
                <div>
                    <h2 id="detail-name"></h2>
                    <div id="detail-meta" class="modal-meta"></div>
                </div>
            </div>
            <button class="modal-close" id="modal-close" aria-label="Close">✕</button>
        </div>
        <div class="modal-body">
            <p id="detail-description" class="modal-description"></p>
            <div class="detail-section">
                <h3>Details</h3>
                <table id="detail-table" class="detail-table"></table>
            </div>
        </div>
        <div class="modal-footer" id="modal-footer"></div>
    </div>
</div>
```

**Step 2: Add detail modal CSS**

```css
.modal {
    position: fixed;
    inset: 0;
    z-index: 300;
    display: flex;
    align-items: center;
    justify-content: center;
}
.modal.hidden { display: none; }
.modal-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(0,0,0,0.6);
    backdrop-filter: blur(4px);
}
.modal-content {
    position: relative;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    width: 600px;
    max-width: 90vw;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: modal-in 0.2s ease;
}
@keyframes modal-in {
    from { opacity: 0; transform: scale(0.95) translateY(8px); }
    to { opacity: 1; transform: scale(1) translateY(0); }
}
.modal-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 24px 24px 16px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
}
.modal-header-left { display: flex; align-items: center; gap: 16px; }
.modal-icon { width: 48px; height: 48px; border-radius: 10px; object-fit: contain; }
.modal-meta { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }
.modal-close {
    background: none; border: none; color: var(--text-secondary);
    cursor: pointer; font-size: 18px; padding: 4px 8px; border-radius: 4px;
    transition: background 0.15s;
}
.modal-close:hover { background: var(--surface-hover); color: var(--text-primary); }
.modal-body { flex: 1; overflow-y: auto; padding: 20px 24px; }
.modal-description { color: var(--text-secondary); font-size: 14px; line-height: 1.6; margin-bottom: 20px; }
.detail-section h3 { font-size: 12px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-secondary); margin-bottom: 12px; }
.detail-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.detail-table tr { border-bottom: 1px solid var(--border); }
.detail-table tr:last-child { border-bottom: none; }
.detail-table td { padding: 8px 4px; }
.detail-table td:first-child { color: var(--text-secondary); width: 40%; font-weight: 500; }
.modal-footer {
    display: flex; gap: 8px; justify-content: flex-end;
    padding: 16px 24px; border-top: 1px solid var(--border); flex-shrink: 0;
}
```

**Step 3: Add detail modal JS to `main.js`**

```javascript
const detailModal = document.getElementById('detail-modal');
const modalClose = document.getElementById('modal-close');
const modalBackdrop = detailModal.querySelector('.modal-backdrop');

function closeModal() { detailModal.classList.add('hidden'); }
modalClose.addEventListener('click', closeModal);
modalBackdrop.addEventListener('click', closeModal);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

window.openPackageDetail = async (pkgId) => {
    // Find the cached pkg data from last rendered list
    const pkg = currentPackages.find(p => p.id === pkgId);
    if (!pkg) return;

    // Populate fixed fields immediately
    document.getElementById('detail-name').textContent = pkg.name;
    document.getElementById('detail-meta').textContent =
        `${pkg.type} · v${pkg.version || 'Unknown'} · ${pkg.publisher || 'Unknown Publisher'}`;
    document.getElementById('detail-description').textContent = pkg.description || 'No description available.';
    document.getElementById('detail-icon').src = pkg.icon_url || '';
    document.getElementById('detail-icon').style.display = pkg.icon_url ? 'block' : 'none';

    // Action button in footer
    const footer = document.getElementById('modal-footer');
    footer.innerHTML = pkg.installed
        ? `<button class="btn btn-danger" onclick="uninstallApp('${pkg.id}', this); closeModal()">Uninstall</button>`
        : `<button class="btn btn-primary" onclick="installApp('${pkg.id}', this); closeModal()">Install</button>`;
    if (pkg.update_available) {
        footer.innerHTML += `<button class="btn btn-primary" onclick="updateApp('${pkg.id}', this); closeModal()">Update</button>`;
    }

    detailModal.classList.remove('hidden');

    // Fetch extended info from backend
    const infoResult = await pyApiCall('get_info', pkgId);
    const table = document.getElementById('detail-table');
    table.innerHTML = '';
    const info = infoResult || {};

    // Add size if available
    if (pkg.size) {
        const sizeRow = table.insertRow();
        sizeRow.insertCell(0).textContent = 'Size';
        sizeRow.insertCell(1).textContent = formatBytes(pkg.size);
    }

    Object.entries(info).forEach(([key, value]) => {
        if (!value) return;
        const row = table.insertRow();
        row.insertCell(0).textContent = key;
        row.insertCell(1).textContent = Array.isArray(value) ? value.join(', ') : String(value);
    });

    if (table.rows.length === 0) {
        table.innerHTML = '<tr><td colspan="2" style="color:var(--text-secondary)">No additional info available.</td></tr>';
    }
};

function formatBytes(bytes) {
    if (!bytes) return 'Unknown';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
    return `${bytes.toFixed(1)} ${units[i]}`;
}
```

**Step 4: Wire card click to open detail in `renderPackages()`**

In `renderPackages()`, add `onclick` to the card element itself (not the action button):

```javascript
card.style.cursor = 'pointer';
card.addEventListener('click', (e) => {
    // Don't trigger if they clicked a button
    if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;
    openPackageDetail(pkg.id);
});
```

**Step 5: Smoke test**

Click any package card (not the Install/Uninstall button). Modal opens with name, version, type, description. Extended info table populates from backend. ESC key and backdrop click close it.

**Step 6: Commit**

```bash
git add bauh/view/web/index.html bauh/view/web/style.css bauh/view/web/main.js
git commit -m "feat: package detail modal with extended info from backend"
```

---

## Task 5: Batch Operations and Update All

**Files:**
- Modify: `bauh/view/web/api.py`
- Modify: `bauh/view/web/index.html`
- Modify: `bauh/view/web/style.css`
- Modify: `bauh/view/web/main.js`

**Context:** "Update All" calls `GenericSoftwareManager.list_updates()` to get all updatable packages then calls `get_upgrade_requirements()` + `upgrade()` in one shot. Batch select allows checking multiple cards then triggering a bulk install/uninstall. The batch UI needs: a multi-select mode toggle, checkboxes on cards, a floating action bar at the bottom showing `N selected — [Uninstall Selected] [Update Selected]`.

**Step 1: Add `update_all` and `batch_update` to `BauhApi`**

```python
def update_all(self) -> dict:
    try:
        result = self.manager.read_installed()
        pkgs_to_update = [p for p in (result.installed or []) if p.update]
        if not pkgs_to_update:
            return {'status': 'ok', 'success': True, 'updated': 0}
        if hasattr(self, 'window') and self.window:
            self.window.evaluate_js(f"terminalOpen('Updating {len(pkgs_to_update)} packages')")
        watcher = WebviewWatcher(self.logger, getattr(self, 'window', None))
        reqs = self.manager.get_upgrade_requirements(pkgs_to_update, root_password=None, watcher=watcher)
        success = self.manager.upgrade(reqs, root_password=None, handler=watcher)
        if hasattr(self, 'window') and self.window:
            self.window.evaluate_js(f"terminalSetDone({str(bool(success)).lower()})")
        return {'status': 'ok', 'success': bool(success), 'updated': len(pkgs_to_update)}
    except Exception as e:
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}

def batch_uninstall(self, pkg_ids: list) -> dict:
    results = []
    for pkg_id in pkg_ids:
        res = self.uninstall(pkg_id)
        results.append({'id': pkg_id, 'success': res.get('success', False)})
    return {'status': 'ok', 'results': results}
```

**Step 2: Add Update All button to topbar in `index.html`**

Inside `.topbar > .filters`:
```html
<button id="update-all-btn" class="btn btn-primary hidden">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="23 4 23 10 17 10"></polyline>
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
    </svg>
    Update All
</button>
<button id="select-mode-btn" class="btn btn-secondary">Select</button>
```

**Step 3: Add batch action bar to `index.html`**

Before closing `</body>`:
```html
<div id="batch-bar" class="batch-bar hidden">
    <span id="batch-count">0 selected</span>
    <div class="batch-actions">
        <button class="btn btn-danger" id="batch-uninstall-btn">Uninstall Selected</button>
        <button class="btn btn-secondary" id="batch-cancel-btn">Cancel</button>
    </div>
</div>
```

**Step 4: Add CSS for batch bar and checkboxes**

```css
.batch-bar {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    z-index: 150;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    animation: slide-up 0.2s ease;
}
.batch-bar.hidden { display: none; }
@keyframes slide-up {
    from { opacity: 0; transform: translateX(-50%) translateY(16px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
}
.package-card.select-mode { cursor: pointer; }
.package-card.select-mode:hover { border-color: var(--accent); }
.package-card.selected { border-color: var(--accent); background: rgba(99,102,241,0.08); }
.pkg-checkbox { display: none; width: 18px; height: 18px; margin-right: 8px; accent-color: var(--accent); }
.package-card.select-mode .pkg-checkbox { display: inline-block; }
```

**Step 5: Add batch logic to `main.js`**

```javascript
let selectMode = false;
let selectedIds = new Set();

const selectModeBtn = document.getElementById('select-mode-btn');
const batchBar = document.getElementById('batch-bar');
const batchCount = document.getElementById('batch-count');
const batchUninstallBtn = document.getElementById('batch-uninstall-btn');
const batchCancelBtn = document.getElementById('batch-cancel-btn');
const updateAllBtn = document.getElementById('update-all-btn');

function enterSelectMode() {
    selectMode = true;
    selectedIds.clear();
    selectModeBtn.textContent = 'Done';
    document.querySelectorAll('.package-card').forEach(card => card.classList.add('select-mode'));
}

function exitSelectMode() {
    selectMode = false;
    selectedIds.clear();
    selectModeBtn.textContent = 'Select';
    batchBar.classList.add('hidden');
    document.querySelectorAll('.package-card').forEach(card => {
        card.classList.remove('select-mode', 'selected');
    });
}

selectModeBtn.addEventListener('click', () => {
    if (selectMode) exitSelectMode(); else enterSelectMode();
});

batchCancelBtn.addEventListener('click', exitSelectMode);

batchUninstallBtn.addEventListener('click', async () => {
    if (!selectedIds.size) return;
    const ids = [...selectedIds];
    exitSelectMode();
    showToast('Uninstalling', `Removing ${ids.length} packages...`, 'info');
    const result = await pyApiCall('batch_uninstall', ids);
    showToast('Done', `Batch uninstall complete`, 'success');
    fetchPackages();
});

updateAllBtn.addEventListener('click', async () => {
    showToast('Updating', 'Starting system update...', 'info');
    const result = await pyApiCall('update_all');
    if (result && result.success) {
        showToast('Success', `Updated ${result.updated} packages`, 'success');
        fetchPackages();
    }
});

// Show Update All button only in updates view
// Modify the nav click handler to show/hide it:
// Inside the navItems click handler, after setting currentView:
// if (currentView === 'updates') { updateAllBtn.classList.remove('hidden'); }
// else { updateAllBtn.classList.add('hidden'); }
```

**Step 6: Wire card checkbox toggling in `renderPackages()`**

Inside `renderPackages()`, add a checkbox to each card and handle toggling:

```javascript
// Add checkbox to card.innerHTML package-header:
<input type="checkbox" class="pkg-checkbox" data-id="${pkg.id}">

// After appending card to grid:
if (selectMode) card.classList.add('select-mode');
const checkbox = card.querySelector('.pkg-checkbox');
card.addEventListener('click', (e) => {
    if (!selectMode) return openPackageDetail(pkg.id);
    if (e.target.tagName === 'BUTTON') return;
    checkbox.checked = !checkbox.checked;
    if (checkbox.checked) { selectedIds.add(pkg.id); card.classList.add('selected'); }
    else { selectedIds.delete(pkg.id); card.classList.remove('selected'); }
    batchCount.textContent = `${selectedIds.size} selected`;
    if (selectedIds.size > 0) batchBar.classList.remove('hidden');
    else batchBar.classList.add('hidden');
});
```

**Step 7: Smoke test**

In Updates view: "Update All" button appears. Clicking it opens terminal panel and runs full system upgrade. In any view: clicking "Select" puts cards in multi-select mode, clicking cards toggles checkboxes, batch bar appears at bottom. "Uninstall Selected" triggers batch operation with terminal output.

**Step 8: Commit**

```bash
git add bauh/view/web/api.py bauh/view/web/index.html bauh/view/web/style.css bauh/view/web/main.js
git commit -m "feat: batch operations, Update All, and multi-select mode"
```

---

## Task 6: Activity / Operation Log

**Files:**
- New: `bauh/view/web/activity_log.py`
- Modify: `bauh/view/web/api.py`
- Modify: `bauh/view/web/index.html`
- Modify: `bauh/view/web/style.css`
- Modify: `bauh/view/web/main.js`

**Context:** Persist a record of every install/uninstall/update operation to `~/.cache/bauh/activity.jsonl`. Each record is a JSON line with `{timestamp, action, pkg_name, pkg_type, success}`. A new "Activity" nav item in the sidebar shows this log as a chronological feed. The log file path is `os.path.expanduser('~/.cache/bauh/activity.jsonl')`.

**Step 1: Create `bauh/view/web/activity_log.py`**

```python
# bauh/view/web/activity_log.py
import json
import os
from datetime import datetime
from typing import List

LOG_PATH = os.path.expanduser('~/.cache/bauh/activity.jsonl')


def record(action: str, pkg_name: str, pkg_type: str, success: bool):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'action': action,
        'pkg_name': pkg_name,
        'pkg_type': pkg_type,
        'success': success,
    }
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(entry) + '\n')


def read_recent(limit: int = 100) -> List[dict]:
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, 'r') as f:
        lines = f.readlines()
    entries = []
    for line in reversed(lines[-limit:]):
        try:
            entries.append(json.loads(line.strip()))
        except json.JSONDecodeError:
            pass
    return entries
```

**Step 2: Call `activity_log.record()` in `BauhApi` after each operation**

In `api.py`, import `activity_log` and add a `record()` call at the end of `install()`, `uninstall()`, `update()`, `update_all()`:

```python
from bauh.view.web import activity_log

# At the end of install(), before returning:
activity_log.record('install', pkg.name, pkg.get_type(), success)

# At the end of uninstall():
activity_log.record('uninstall', pkg.name, pkg.get_type(), success)

# At the end of update():
activity_log.record('update', pkg.name, pkg.get_type(), success)

# At the end of update_all():
activity_log.record('update_all', f'{updated} packages', 'all', bool(success))
```

Add `get_activity` method:
```python
def get_activity(self) -> dict:
    try:
        from bauh.view.web import activity_log
        entries = activity_log.read_recent(100)
        return {'status': 'ok', 'data': entries}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
```

**Step 3: Add Activity nav item to `index.html`**

In the sidebar nav (after the Settings button):
```html
<button class="nav-item" data-view="activity">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
    </svg>
    Activity
</button>
```

**Step 4: Add activity feed CSS**

```css
.activity-feed { display: flex; flex-direction: column; gap: 8px; padding: 8px 0; }
.activity-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 13px;
}
.activity-icon { width: 28px; height: 28px; border-radius: 6px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.activity-icon.success { background: rgba(34,197,94,0.15); color: var(--success); }
.activity-icon.error { background: rgba(239,68,68,0.15); color: var(--error); }
.activity-body { flex: 1; }
.activity-action { font-weight: 600; text-transform: capitalize; }
.activity-pkg { color: var(--text-secondary); }
.activity-time { color: var(--text-secondary); font-size: 11px; flex-shrink: 0; }
```

**Step 5: Add activity view rendering to `main.js`**

Inside the nav item click handler, handle `currentView === 'activity'`:

```javascript
} else if (currentView === 'activity') {
    packagesGrid.style.display = 'block';
    emptyState.classList.add('hidden');
    loadingState.classList.remove('hidden');
    packagesGrid.innerHTML = '';

    const result = await pyApiCall('get_activity');
    loadingState.classList.add('hidden');
    const entries = result || [];

    if (!entries.length) {
        packagesGrid.innerHTML = '<div style="padding:32px;color:var(--text-secondary)">No activity recorded yet.</div>';
        return;
    }

    const feed = document.createElement('div');
    feed.className = 'activity-feed';

    entries.forEach(entry => {
        const item = document.createElement('div');
        item.className = 'activity-item';
        const iconClass = entry.success ? 'success' : 'error';
        const iconChar = entry.success ? '✓' : '✗';
        const time = new Date(entry.timestamp).toLocaleString();
        item.innerHTML = `
            <div class="activity-icon ${iconClass}">${iconChar}</div>
            <div class="activity-body">
                <span class="activity-action">${entry.action}</span>
                <span class="activity-pkg"> — ${entry.pkg_name}</span>
                <span class="tag ${(entry.pkg_type || '').toLowerCase()}" style="margin-left:8px">${entry.pkg_type}</span>
            </div>
            <div class="activity-time">${time}</div>
        `;
        feed.appendChild(item);
    });

    packagesGrid.appendChild(feed);
}
```

**Step 6: Smoke test**

Run app. Perform an install or uninstall. Navigate to Activity tab. Entry appears with timestamp, action type, package name, gem type badge, and success/failure indicator. Oldest-first entries appear at bottom, newest at top.

**Step 7: Commit**

```bash
git add bauh/view/web/activity_log.py bauh/view/web/api.py \
        bauh/view/web/index.html bauh/view/web/style.css bauh/view/web/main.js
git commit -m "feat: persistent activity log with chronological feed view"
```

---

## Verification Plan

### After Each Task
Run:
```bash
source venv/bin/activate && python -m bauh.app --logs
```
Expected: No Python traceback. Log shows gem backends loading. UI renders per task spec.

### Final Integration Check
After all 6 tasks:
1. Dashboard shows real suggestions from live repos
2. Installed tab shows real system packages (AUR, Flatpak, Snap present)
3. Updates tab shows packages with pending updates; Update All button visible
4. Clicking a package card opens detail modal with real info from backend
5. Install/Uninstall/Update opens terminal panel with live output lines
6. Progress bar fills during operation, "✓ Completed" appears on finish
7. Select mode: checkboxes appear on cards, batch uninstall works
8. Activity tab shows log of all operations performed
