# Crimson & Obsidian UI Modernization Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Modernize the Atlas pywebview front-end visual aesthetic and user experience, replacing the generic indigo colors with a custom Obsidian & Crimson theme matching the new app icon, and introducing premium skeleton loaders and fluid animations.

**Architecture:** Overhaul HSL color tokens and layout styles inside `style.css` to build an elegant glassmorphism foundation. Update the loading lifecycle in `main.js` to render a grid of animated skeleton cards in `packagesGrid` when loading starts, ensuring visual continuity and a premium feel.

**Tech Stack:** HTML5, Vanilla CSS3 (variables, transitions, animations, backdrop-filters), and clientside Vanilla ES6 Javascript.

---

### Task 1: Rebuild CSS Custom Properties & Core Color Tokens
Redefine the light and dark theme colors to adopt the obsidian black base and glowing ruby-crimson branding.

**Files:**
- Modify: `atlas/view/webview/style.css:1-46`

**Step 1: Write the updated variables and obsidian/crimson theme tokens**
Replace the root/dark variable tokens at the very top of `style.css` with the Crimson and Obsidian variables:
```css
:root {
    /* Light Theme Tokens */
    --bg-base: #f4f6fa;
    --bg-surface: #ffffff;
    --bg-surface-glass: rgba(255, 255, 255, 0.75);
    --bg-surface-hover: #f1f5f9;
    --border-color: #e2e8f0;
    --text-primary: #0f172a;
    --text-secondary: #64748b;
    --accent-color: #e02424;           /* Premium Crimson */
    --accent-hover: #c81e1e;           /* Deeper Crimson */
    --accent-glass: rgba(224, 36, 36, 0.12);
    
    /* Status Colors */
    --status-success: #10b981;
    --status-warning: #f59e0b;
    --status-danger: #ef4444;

    /* Metrics */
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --sidebar-width: 260px;
    --shadow-sm: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    --shadow-md: 0 4px 12px -1px rgba(0, 0, 0, 0.08);
    --shadow-glass: 0 8px 32px 0 rgba(0, 0, 0, 0.05);
    
    /* Animation */
    --transition-fast: 0.15s ease-in-out;
    --transition-smooth: 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

[data-theme="dark"] {
    --bg-base: #05070c;               /* Obsidian Black */
    --bg-surface: #0e111a;            /* Deep Graphite */
    --bg-surface-glass: rgba(14, 17, 26, 0.75);
    --bg-surface-hover: #161a26;
    --border-color: rgba(255, 255, 255, 0.06);
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent-color: #e02424;           /* Glowing Crimson */
    --accent-hover: #ff3333;           /* Vivid Crimson hover */
    --accent-glass: rgba(224, 36, 36, 0.16);
    --shadow-glass: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
}
```

**Step 2: Commit Task 1**
Run:
```bash
git add atlas/view/webview/style.css
git commit -m "feat: redefine core HSL variables with Crimson and Obsidian design tokens"
```
Expected: git commit output.

---

### Task 2: Implement Skeleton Loader Screens
Construct a rich, responsive CSS shimmer skeleton screen system to replace the standard load spinner.

**Files:**
- Modify: `atlas/view/webview/style.css` (append styles)
- Modify: `atlas/view/webview/main.js` (inject skeletons)

**Step 1: Add Shimmer and Skeleton card styles to `style.css`**
Append these styles to `style.css`:
```css
/* Skeleton Loader Styles */
.skeleton-card {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    height: 180px;
    position: relative;
    overflow: hidden;
}
.skeleton-header {
    display: flex;
    align-items: center;
    gap: 16px;
}
.skeleton-icon {
    width: 48px;
    height: 48px;
    border-radius: var(--radius-sm);
    flex-shrink: 0;
}
.skeleton-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.skeleton-line {
    height: 12px;
    border-radius: var(--radius-sm);
}
.skeleton-line.title {
    width: 60%;
    height: 16px;
}
.skeleton-line.subtitle {
    width: 40%;
}
.skeleton-line.description {
    width: 90%;
    height: 10px;
}
.skeleton-line.description-short {
    width: 75%;
    height: 10px;
}
.skeleton-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: auto;
    padding-top: 16px;
    border-top: 1px solid var(--border-color);
}
.skeleton-tag {
    width: 70px;
    height: 20px;
    border-radius: var(--radius-sm);
}
.skeleton-btn {
    width: 80px;
    height: 28px;
    border-radius: var(--radius-md);
}
.skeleton-shimmer {
    background: linear-gradient(90deg, var(--bg-surface-hover) 25%, var(--border-color) 50%, var(--bg-surface-hover) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite linear;
}
@keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}
```

**Step 2: Add skeleton injection logic to `main.js`**
Add the helper function `getSkeletonGridHTML()` at the bottom or helper section of `main.js`:
```javascript
function getSkeletonGridHTML() {
    let html = '';
    for (let i = 0; i < 6; i++) {
        html += `
        <div class="skeleton-card">
            <div class="skeleton-header">
                <div class="skeleton-icon skeleton-shimmer"></div>
                <div class="skeleton-info">
                    <div class="skeleton-line title skeleton-shimmer"></div>
                    <div class="skeleton-line subtitle skeleton-shimmer"></div>
                </div>
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 8px;">
                <div class="skeleton-line description skeleton-shimmer"></div>
                <div class="skeleton-line description-short skeleton-shimmer"></div>
            </div>
            <div class="skeleton-footer">
                <div class="skeleton-tag skeleton-shimmer"></div>
                <div class="skeleton-btn skeleton-shimmer"></div>
            </div>
        </div>`;
    }
    return html;
}
```

**Step 3: Hook skeleton loader into `fetchPackages` state**
Modify `fetchPackages()` in `main.js` so it displays skeletons in `packagesGrid` when loading packages:
```javascript
async function fetchPackages() {
    // Show skeleton grid inside packagesGrid instead of hiding it
    packagesGrid.style.display = 'grid';
    packagesGrid.innerHTML = getSkeletonGridHTML();
    
    emptyState.classList.add('hidden');
    loadingState.classList.add('hidden'); // keep traditional spinner hidden
```

**Step 4: Commit Task 2**
Run:
```bash
git add atlas/view/webview/style.css atlas/view/webview/main.js
git commit -m "feat: implement animated skeleton loader screens for application listings"
```
Expected: git commit output.

---

### Task 3: Sidebar & Topbar Glassmorphic Modernization
Enhance sidebar navigation, search focus, and dropdown controls with transparent borders and crimson glows.

**Files:**
- Modify: `atlas/view/webview/style.css`

**Step 1: Implement glassmorphism styles on Sidebar**
Modify the `.sidebar` class in `style.css` to add backdrop-filter, custom border-right, and deep crimson indicators for active nav items.
```css
.sidebar {
    width: var(--sidebar-width);
    background-color: var(--bg-surface-glass);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    z-index: 10;
    transition: background-color var(--transition-smooth), border-color var(--transition-smooth);
}
```
Update active navigation items to use a clean glowing red cue:
```css
.nav-item.active {
    background-color: var(--accent-glass);
    color: var(--accent-color);
    box-shadow: inset 3px 0 0 var(--accent-color);
}
```

**Step 2: Polish Top Bar elements**
Modernize search input focus glow and select dropdown style:
```css
#search-input:focus {
    outline: none;
    border-color: var(--accent-color);
    box-shadow: 0 0 16px var(--accent-glass);
}
```

**Step 3: Commit Task 3**
Run:
```bash
git add atlas/view/webview/style.css
git commit -m "style: modernize sidebar glassmorphism and topbar controls with crimson active states"
```

---

### Task 4: Package Cards visual polish & micro-animations
Modernize package cards using high-fidelity cubic-bezier transitions, elevation hovers, and animated entrance fades.

**Files:**
- Modify: `atlas/view/webview/style.css`

**Step 1: Upgrade `.package-card` styling and hovers**
Apply the glassmorphic background to cards and set up the entrance animations and smooth hover transitions:
```css
.package-card {
    background-color: var(--bg-surface-glass);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    box-shadow: var(--shadow-sm);
    transition: transform var(--transition-smooth), box-shadow var(--transition-smooth), border-color var(--transition-smooth);
    cursor: default;
    position: relative;
    overflow: hidden;
    animation: fadeInUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

.package-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 10px 24px rgba(224, 36, 36, 0.08);
    border-color: rgba(224, 36, 36, 0.3);
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(12px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}
```

**Step 2: Commit Task 4**
Run:
```bash
git add atlas/view/webview/style.css
git commit -m "style: add glassmorphism to package cards, elegant hovers, and fadeInUp entrance animations"
```

---

### Task 5: Upgrade Modal backdrops and spring entries
Polish operational modal dialogue boxes with high-intensity backdrop blur and dynamic, spring-like scale transitions.

**Files:**
- Modify: `atlas/view/webview/style.css`

**Step 1: Update `.modal-backdrop` and `.modal-content` animation**
Increase backdrop blur and apply a sleek cubic-bezier scale transition to the modal cards:
```css
.modal-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(5, 7, 12, 0.7); /* Obsidian overlay */
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
}

.modal-content {
    position: relative;
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    width: 600px;
    max-width: 90vw;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: modal-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
    box-shadow: var(--shadow-glass);
}

@keyframes modal-in {
    from {
        opacity: 0;
        transform: scale(0.95) translateY(16px);
    }
    to {
        opacity: 1;
        transform: scale(1) translateY(0);
    }
}
```

**Step 2: Commit Task 5**
Run:
```bash
git add atlas/view/webview/style.css
git commit -m "style: upgrade modal dialogs with deep glass backdrops and spring scale transitions"
```

---

### Task 6: Complete Python Test Suit Validation
Verify that the full backend python tests remain 100% green with no regressions.

**Step 1: Execute pytest command**
Run: `venv/bin/pytest`
Expected: 183 passed, 0 failed.

**Step 2: Commit Task 6**
Run:
```bash
git commit --allow-empty -m "test: verify complete test suite passes following visual modernization pass"
```
