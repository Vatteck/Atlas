# Design Document: Atlas UI Modernization & Premium Polish

**Date:** 2026-06-01  
**Status:** Approved  
**Author:** Core Daemon  

---

## 1. Goal
Overhaul the visual aesthetic and user experience of the Atlas pywebview front-end, transforming it from a standard layout into a highly premium, modern, glassmorphic experience. The visual language will be directly unified with the brand-new Crimson/Obsidian app icon, providing an immersive, high-performance visual brand.

---

## 2. Architecture & Design Specifications

### 2.1. The Crimson & Obsidian Palette (CSS Custom Properties)
We will transition from the generic indigo accents to a custom-tailored dark Obsidian base with premium neon-ruby and glowing crimson highlights.

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
    --accent-hover: #ff3333;           /* Vivid Crimson for Dark Mode hover */
    --accent-glass: rgba(224, 36, 36, 0.16);
    --shadow-glass: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
}
```

### 2.2. Skeleton Loader System
Instead of a single spinner centered on screen, the loading state will show a modern, responsive grid of shimmer-animated cards mimicking actual application cards.

- **HTML Structure:** A helper `getSkeletonGridHTML()` in `main.js` generates 6 placeholders matching the exact structural layout of `.package-card`.
- **CSS Shimmer Effect:**
  ```css
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

### 2.3. Glassmorphic Sidebar & Aligned Header
- **Sidebar:** Styled with a solid `backdrop-filter: blur(20px)`, transparent border treatment, custom shadow-glows, and crimson active cues.
- **Header:** Exact horizontal grid alignment for search bar, filters, select dropdowns, and batch operations. Accent borders and crimson halo on focus.

### 2.4. Card Visuals & Entrance Animations
- **Cards:** Glassmorphism treatments (`background: var(--bg-surface-glass)`). High-performance CSS transform and opacity entries:
  ```css
  @keyframes fadeInUp {
      from {
          opacity: 0;
          transform: translateY(16px);
      }
      to {
          opacity: 1;
          transform: translateY(0);
      }
  }
  ```
- **Hover Micro-Animations:** Subtle 3D lift (`transform: translateY(-4px)`) paired with a crimson halo shadow.

### 2.5. Dialog & Modal Transition Upgrades
- Backdrop blur expanded to `8px` with a dark `rgba(0, 0, 0, 0.7)` overlay to ensure total user focus on operations.
- Modals scale and rise with an elegant spring-curve (`cubic-bezier(0.34, 1.56, 0.64, 1)` or custom bezier).

---

## 3. Verification & Testing Plan

### 3.1. Automated Verification
- Ensure the full Python test suite (`python -m pytest`) passes.
- Validate there are no broken Javascript console exceptions or CSS errors.

### 3.2. Manual Verification
- Deploy and verify visually in the WebKitGTK pywebview application.
- Check both Dark and Light theme toggle states.
- Confirm modal dialogue rendering works exactly, ensuring checkboxes, combos, and text blocks render accurately and return outputs successfully.
