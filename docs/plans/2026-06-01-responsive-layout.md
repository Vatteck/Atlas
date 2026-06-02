# Responsive Layout Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Enable fluid responsive adaptivity for Atlas down to 320px width to support tiling window managers and small screen form factors perfectly.

**Architecture:** We use viewport-based CSS media queries (`@media`) to dynamically modify variables, layout structures (sidebar compaction, topbar wrapping, grid columns), and component spacing. We wrap HTML nav labels in `<span>` tags to allow clean visual toggling.

**Tech Stack:** Vanilla HTML5, Modern CSS Grid & Flexbox, pywebview.

---

### Task 1: HTML Nav Label Isolation

**Files:**
- Modify: `atlas/view/webview/index.html`
- Verification: `pytest tests/view/webview/`

**Step 1: Write HTML changes**
We will modify `/home/vatteck/Projects/Atlas/atlas/view/webview/index.html` to wrap navigation text labels in `<span class="nav-label">` to allow targeted styling control, and wrap the updates label similarly.

Target blocks in `index.html` (nav buttons):
```html
<button class="nav-item active" data-view="dashboard">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
    <span class="nav-label">Dashboard</span>
</button>
<button class="nav-item" data-view="installed">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
    <span class="nav-label">Installed</span>
</button>
<button class="nav-item" data-view="updates">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
    <span class="nav-label">Updates</span> <span class="badge" id="updates-badge">0</span>
</button>
<button class="nav-item" data-view="disk">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 8v4l3 3"></path></svg>
    <span class="nav-label">Disk</span>
</button>
<button class="nav-item" data-view="activity">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
    <span class="nav-label">Activity</span>
</button>
<button class="nav-item" data-view="settings">
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
    <span class="nav-label">Settings</span>
</button>
```

**Step 2: Run verification tests**
Run the existing webview test suite to make sure no regressions occur in JS parsing or watcher APIs:
```bash
python -m pytest tests/view/webview/ -v
```
Expected: PASS

**Step 3: Commit**
```bash
git add atlas/view/webview/index.html
git commit -m "refactor: wrap navigation item labels in span for responsive styling control"
```

---

### Task 2: Compact Sidebar Layout CSS

**Files:**
- Modify: `atlas/view/webview/style.css`
- Verification: `python -m pytest`

**Step 1: Write CSS media query rules**
We will append the sidebar collapse rules inside `@media (max-width: 768px)` in `/home/vatteck/Projects/Atlas/atlas/view/webview/style.css`.

CSS to add:
```css
@media (max-width: 768px) {
    :root {
        --sidebar-width: 70px;
    }
    
    .sidebar-header {
        padding: 20px 0;
        justify-content: center;
    }
    
    .sidebar-header h1 {
        display: none;
    }
    
    .sidebar-nav {
        padding: 8px;
    }
    
    .nav-item {
        justify-content: center;
        padding: 12px;
        gap: 0;
    }
    
    .nav-item .nav-label {
        display: none;
    }
    
    /* Absolute overlay badge on compact updates icon */
    .nav-item .badge {
        position: absolute;
        top: 4px;
        right: 8px;
        margin-left: 0;
        padding: 2px 6px;
        font-size: 9px;
        border: 1.5px solid var(--bg-sidebar);
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    
    .sidebar-footer {
        padding: 12px 4px;
    }
    
    .sidebar-footer-icons {
        flex-direction: column;
        align-items: center;
        gap: 12px;
        margin-top: 0;
    }
}
```

**Step 2: Run verification tests**
```bash
python -m pytest -q
```
Expected: PASS

**Step 3: Commit**
```bash
git add atlas/view/webview/style.css
git commit -m "style: implement compact sidebar layout under 768px media query"
```

---

### Task 3: Topbar Responsive Wrap & Stacking CSS

**Files:**
- Modify: `atlas/view/webview/style.css`
- Verification: `python -m pytest`

**Step 1: Add Topbar CSS rules**
We will append the topbar adaptivity rules under the `@media (max-width: 768px)` and `@media (max-width: 600px)` queries in `style.css`.

CSS to add:
```css
@media (max-width: 768px) {
    .topbar {
        padding: 12px 16px;
        gap: 12px;
        flex-wrap: wrap;
    }
    
    #search-input {
        padding: 10px 12px 10px 40px;
        font-size: 14px;
        border-radius: var(--radius-md);
    }
    
    .styled-select {
        padding: 10px 32px 10px 12px;
        border-radius: var(--radius-md);
        font-size: 13px;
        background-position: right 8px center;
    }
    
    .btn {
        padding: 7px 12px;
        font-size: 12px;
        border-radius: var(--radius-md);
    }
}

@media (max-width: 600px) {
    .topbar {
        flex-direction: column;
        align-items: stretch;
    }
    
    .search-container {
        width: 100%;
        order: 1;
    }
    
    .topbar #refresh-btn {
        display: none; /* Hide refresh button on extra narrow views to save horizontal width */
    }
    
    .filters {
        width: 100%;
        order: 2;
        justify-content: space-between;
        gap: 6px;
    }
    
    .filters .styled-select {
        flex: 1;
        max-width: unset;
    }
}
```

**Step 2: Run verification tests**
```bash
python -m pytest -q
```
Expected: PASS

**Step 3: Commit**
```bash
git add atlas/view/webview/style.css
git commit -m "style: implement topbar wrap and vertical stacking for narrow widths"
```

---

### Task 4: Package Grid, Cards, and Modals Density CSS

**Files:**
- Modify: `atlas/view/webview/style.css`
- Verification: `python -m pytest`

**Step 1: Add Grid, Cards, and Modal CSS rules**
We will append the grid scaling and modal scaling rules in the media queries in `style.css`.

CSS to add:
```css
@media (max-width: 768px) {
    .packages-grid {
        padding: 12px;
        gap: 12px;
    }
    
    .disk-view-container,
    .settings-page,
    .activity-feed {
        padding: 16px;
    }
    
    .disk-summary-card {
        padding: 20px;
    }
    
    .disk-summary-value {
        font-size: 32px;
    }
}

@media (max-width: 480px) {
    .packages-grid {
        grid-template-columns: 1fr;
    }
    
    .package-card {
        padding: 12px;
    }
    
    .package-header {
        gap: 12px;
    }
    
    .package-icon {
        width: 40px;
        height: 40px;
    }
    
    .package-title {
        font-size: 15px;
    }
    
    .package-footer {
        flex-direction: column;
        align-items: stretch;
        gap: 12px;
    }
    
    .package-footer > div:last-child {
        width: 100%;
        display: flex;
        gap: 8px;
    }
    
    .package-footer .btn {
        flex: 1;
    }
    
    .modal-content {
        max-height: 92vh;
    }
    
    .modal-header {
        padding: 16px;
    }
    
    .modal-body {
        padding: 16px;
    }
    
    .modal-footer {
        padding: 12px 16px;
    }
}
```

**Step 2: Run verification tests**
```bash
python -m pytest -q
```
Expected: PASS

**Step 3: Commit**
```bash
git add atlas/view/webview/style.css
git commit -m "style: optimize packages grid, cards, and modal layouts for small screens"
```
