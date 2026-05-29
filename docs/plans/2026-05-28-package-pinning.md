# Package Pinning / Update Hold Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Implement package pinning (update hold/ignore) in the Bauh web UI so users can prevent specific installed packages from receiving updates.

**Architecture:** Extend package serialization in `bauh/view/web/api.py` with pinning support attributes. Add `pin_update` and `unpin_update` API endpoints calling the software manager's existing ignore features. Style a new "Pin" button in `style.css` and render/handle it dynamically in the card builder in `main.js`.

**Tech Stack:** Python 3.14, Vanilla HTML/CSS/JS, unittest

---

### Task 1: Python Bridge Changes

**Files:**
- Modify: [api.py](file:///home/vatteck/git/bauh/bauh/view/web/api.py)
- Test: [test_api.py](file:///home/vatteck/git/bauh/tests/view/web/test_api.py)

**Step 1: Modify `_serialize_pkg`**
Extend the dictionary returned by `_serialize_pkg` to include pinning properties:
```python
'update_ignored': pkg.is_update_ignored() if hasattr(pkg, 'is_update_ignored') else False,
'supports_pinning': pkg.supports_ignored_updates() if hasattr(pkg, 'supports_ignored_updates') else False,
```

**Step 2: Add `pin_update` and `unpin_update` to `BauhApi`**
Add the following methods to the `BauhApi` class:
```python
    def pin_update(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            self.manager.ignore_update(pkg)
            self.logger.info(f"Pinned package: {pkg.name}")
            return {'status': 'ok', 'success': True}
        except Exception as e:
            self.logger.error(f"Error pinning package {pkg.name}: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def unpin_update(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            self.manager.revert_ignored_update(pkg)
            self.logger.info(f"Unpinned package: {pkg.name}")
            return {'status': 'ok', 'success': True}
        except Exception as e:
            self.logger.error(f"Error unpinning package {pkg.name}: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}
```

---

### Task 2: CSS Styling

**Files:**
- Modify: [style.css](file:///home/vatteck/git/bauh/bauh/view/web/style.css)

**Step 1: Append pin button styling**
Append the following styles to [style.css](file:///home/vatteck/git/bauh/bauh/view/web/style.css):
```css
.btn-pin {
    background: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    font-size: 12px;
    padding: 5px 10px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}
.btn-pin:hover { background: var(--bg-surface-hover); color: var(--text-primary); }
.btn-pin.pinned { background: rgba(245, 158, 11, 0.1); border-color: var(--status-warning); color: var(--status-warning); }
.btn-pin.pinned:hover { background: var(--status-warning); color: white; }
```

---

### Task 3: Frontend Script Changes

**Files:**
- Modify: [main.js](file:///home/vatteck/git/bauh/bauh/view/web/main.js)

**Step 1: Construct and inject pin button**
Construct `pinButton` when rendering packages in `renderPackages(packages)` if `pkg.installed && pkg.supports_pinning`:
```javascript
        const pinButton = (pkg.installed && pkg.supports_pinning) ?
            `<button class="btn btn-pin ${pkg.update_ignored ? 'pinned' : ''} action-btn"
                data-action="${pkg.update_ignored ? 'unpin' : 'pin'}"
                data-id="${escapeHtml(pkg.id)}"
                title="${pkg.update_ignored ? 'Click to allow updates' : 'Click to hold (pin) this version'}">
                ${pkg.update_ignored ? '📌 Pinned' : '📌 Pin'}
             </button>` : '';
```
Inject `pinButton` alongside `actionButton` in the card footer:
```html
            <div class="package-footer">
                <div class="package-tags">
                    <span class="tag ${escapeHtml(pkg.type.toLowerCase())}">${escapeHtml(pkg.type)}</span>
                </div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    ${pinButton}
                    ${actionButton}
                </div>
            </div>
```

**Step 2: Refactor event listener binding block**
Select all `.action-btn` elements inside the package card and attach click listeners:
```javascript
        card.querySelectorAll('.action-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                const pid = btn.dataset.id;
                
                if (operationInProgress) {
                    showToast('Busy', 'Another operation is already running', 'warning');
                    return;
                }
                
                btn.classList.add('loading');
                
                if (action === 'pin') {
                    const res = await pyApiCall('pin_update', pid);
                    if (res) {
                        showToast('Pinned', 'Package pinned successfully', 'success');
                        fetchPackages();
                    } else {
                        btn.classList.remove('loading');
                    }
                } else if (action === 'unpin') {
                    const res = await pyApiCall('unpin_update', pid);
                    if (res) {
                        showToast('Unpinned', 'Package unpinned successfully', 'success');
                        fetchPackages();
                    } else {
                        btn.classList.remove('loading');
                    }
                } else if (action === 'install') {
                    installApp(pid, btn);
                } else if (action === 'uninstall') {
                    uninstallApp(pid, btn);
                } else if (action === 'update') {
                    updateApp(pid, btn);
                }
            });
        });
```

**Step 3: Update `mockApi`**
Add `pin_update` and `unpin_update` methods to `mockApi`:
```javascript
    pin_update: async (id) => { return new Promise(resolve => setTimeout(() => resolve({success: true}), 500)); },
    unpin_update: async (id) => { return new Promise(resolve => setTimeout(() => resolve({success: true}), 500)); },
```

---

### Task 4: Unit Testing & Verification

**Files:**
- Modify: [test_api.py](file:///home/vatteck/git/bauh/tests/view/web/test_api.py)

**Step 1: Add unit tests**
Implement `BauhApiPinTest` to verify success and failure of `pin_update` and `unpin_update` methods:
```python
class BauhApiPinTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = BauhApi(self.manager, self.logger)
        
        self.pkg = Mock()
        self.pkg.name = "test-pin-pkg"
        self.api.pkg_registry["test-id"] = self.pkg

    def test_pin_update_success(self):
        res = self.api.pin_update("test-id")
        self.assertEqual(res, {'status': 'ok', 'success': True})
        self.manager.ignore_update.assert_called_once_with(self.pkg)

    def test_pin_update_not_found(self):
        res = self.api.pin_update("unknown-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Unknown package id", res['message'])

    def test_pin_update_error(self):
        self.manager.ignore_update.side_effect = Exception("Pin failed")
        res = self.api.pin_update("test-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Pin failed", res['message'])

    def test_unpin_update_success(self):
        res = self.api.unpin_update("test-id")
        self.assertEqual(res, {'status': 'ok', 'success': True})
        self.manager.revert_ignored_update.assert_called_once_with(self.pkg)

    def test_unpin_update_not_found(self):
        res = self.api.unpin_update("unknown-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Unknown package id", res['message'])

    def test_unpin_update_error(self):
        self.manager.revert_ignored_update.side_effect = Exception("Unpin failed")
        res = self.api.unpin_update("test-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Unpin failed", res['message'])
```

**Step 2: Run verification**
Run the tests:
`venv/bin/python -m unittest tests/view/web/test_api.py`

**Step 3: Commit**
`git add bauh/view/web/api.py bauh/view/web/style.css bauh/view/web/main.js tests/view/web/test_api.py`
`git commit -m "feat: add package pinning (update hold) support"`
