# Responsive Layout Design

Design for adaptive layouts to support small screens, tiling window managers, and constrained viewports.

## Goal
Make the Atlas pywebview front-end adapt elegantly to smaller viewports and tiling window manager split views down to 320px width.

## Scope
- Refactor structural HTML nav labels in `atlas/view/webview/index.html` to enable granular target toggling.
- Implement pure CSS media queries in `atlas/view/webview/style.css` to handle sidebar compaction, topbar wrapping/stacking, package card layout density, and modal viewport scaling.

## Design Details

### 1. Compact Sidebar Layout (Viewport <= 768px)
- Redefine `--sidebar-width` to `70px` (was `260px`).
- Hide sidebar logo text `<h1>Atlas</h1>` and center the `.logo` image.
- Add `<span class="nav-label">` to `index.html` nav item labels and apply `display: none` to hide them in compact view.
- Center nav item icons.
- Stack footer icons (Theme Toggle, Shortcuts) vertically.
- Transform the updates badge into an absolute-positioned notification dot overlapping the top-right corner of the updates icon.

### 2. Topbar Wrap & Stack
- **Viewport <= 768px**:
  - Reduce padding to `12px 16px` and gap to `12px`.
  - Enable `flex-wrap: wrap`.
- **Viewport <= 600px**:
  - Full-width search bar: `.search-container { min-width: 100%; order: 1; }`
  - Wrap filters to the second row: `.filters { min-width: 100%; justify-content: space-between; order: 2; }`

### 3. Packages Grid & Cards Density
- **Viewport <= 768px**:
  - Reduce grid padding to `12px` and gaps to `12px`.
- **Viewport <= 480px**:
  - Force single column grid: `grid-template-columns: 1fr`.
  - Reduce package card interior padding to `12px` to maximize space.

### 4. Modal Scale & Layout Stability
- Ensure modal dialogs resize gracefully down to `92vw` with a maximum height of `90vh`.
- Keep `.modal-body` scrollable to prevent any vertical overflow or button clipping.

## Verification
- Resize GUI to narrow splits (e.g. 400px, 600px) and verify sidebar collapses, search/filters wrap, and grid items lay out beautifully.
- Verify mouse & keyboard interactions (navigating items, searching, filtering) operate correctly when minimized.
