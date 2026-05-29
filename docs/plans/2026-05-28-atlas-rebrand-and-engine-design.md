# Design Document: Atlas Rebranding and Core Engine Optimization

This document outlines the architectural changes, file purges, namespace renames, and background performance optimizations required to transition from `bauh` to **Atlas** (under the `atlaspm` / `atlas-pm` system namespace) in a clean, separate repository.

---

## 1. Directory Purge (Legacy Code Cleanup)

To start with a lean, modern repository, we will completely remove the legacy Qt5 codebase.

### Deleted Paths:
- `bauh/view/qt/` (Purge the entire folder hierarchy containing Qt forms, widgets, themes, and layouts)
- `bauh/view/resources/style/` (Remove all custom QSS style assets)
- `tests/view/qt/` (Remove legacy Qt view tests)

### Maintained Paths:
- `bauh/view/web/` (The new modern webview UI layout, style, and scripts)
- `bauh/view/core/` (Abstract core controller connecting GUI actions to gems)
- `bauh/gems/` (All package manager backends: AppImage, Arch, Debian, Flatpak, Snap, Web)
- `bauh/commons/` (Common system utilities)

---

## 2. Codebase Rebranding (Namespace Renaming)

We will execute a global namespace renaming across the entire codebase to transition fully to the new brand.

### Renaming Operations:
1. **Directory Rename:** Rename the root package directory `bauh/` to `atlas/`.
2. **Bridge Directory Rename:** Rename `atlas/view/web/` to `atlas/view/webview/` for modern alignment.
3. **Module Imports:**
   - Find and replace all occurrences of `import bauh` or `from bauh` with `import atlas` or `from atlas`.
4. **Configuration Paths:**
   - Change `~/.config/bauh/` to `~/.config/atlaspm/`
   - Change `~/.cache/bauh/` to `~/.cache/atlaspm/`
   - Change `/tmp/bauh@$USER` to `/tmp/atlaspm@$USER`
   - Change `/var/cache/bauh` to `/var/cache/atlaspm`
5. **UI & Brand assets:**
   - In `index.html`, replace references to "bauh" in head titles, welcome screens, and sidebar details.
   - Update icons, brand colors, and logging prefix keys.

---

## 3. Concurrency and Lazy Gem Initialization

To achieve maximum performance and sub-second launch times, we will re-engineer the background initialization sequence of package managers (gems).

### Performance Refactorings:
1. **Lazy Backend Preparation:**
   - Currently, `GenericSoftwareManager.prepare()` eagerly initializes all package gems (Arch, Flatpak, Snap, AppImage) at boot, causing significant blocking and wait time.
   - We will modify `GenericSoftwareManager` or `BauhApi` (now `AtlasApi`) to initialize gems lazily when their respective views are requested, or query only enabled gems configured in `~/.config/atlaspm/config.yml`.
2. **Asynchronous ThreadPoolExecutor:**
   - Standardize all thread spawns in `api.py` (now `api.py` under `atlas/view/webview/`) using a shared `ThreadPoolExecutor` or `asyncio` execution model to streamline concurrent API requests and prevent UI freezes.

---

## 4. Verification Plan

### Automated Verification:
- Discover and run all unit tests on the new `atlas` namespace:
  `python -m unittest discover -s tests`

### Manual Verification:
- Launch Atlas using the new command wrapper:
  `python -m atlas.app --logs`
- Verify that standard navigation (Installed, Updates, Suggestions, Search) works perfectly under the new namespace.
- Check configuration folders and verify new logs and cache files are cleanly created in `~/.config/atlaspm` and `~/.cache/atlaspm`.
