# Browse by Category — store-like discovery view

**Date:** 2026-06-02
**Status:** shipped (backend + frontend + tests; awaiting a GUI eyeball)
**Backlog item:** "Browse by category" (docs/BACKLOG.md → Discovery & detail)

## Goal

A store-like **Browse** page: pick a category (Games, Graphics, Internet, …) and see a
grid of packages in it. Uses the category data Atlas already ships and caches — no new
data source, no per-package network fan-out.

## What data we already have

- `atlas-files@main/arch/categories.txt` → cached at `~/.cache/atlaspm/arch/categories.txt`,
  downloaded by `commons/category.CategoriesDownloader` and parsed into the Arch gem's
  `self.categories: Dict[str, List[str]]` (**package name → [raw category labels]**), e.g.
  `0ad=Game`, `alsa-lib=Audio,System`. ~295 curated entries today.
- Raw labels are messy / inconsistent-case (`Browser`+`browser`, `Xfce`+`XFCE`, `Python`,
  `Emulator`, `Manjaro`, …). They were authored to *annotate* search results, not as a
  browse index — so we normalize them into a small curated set of top-level buckets.
- Lightweight repo resolution already exists: `pacman.map_available_packages()` (`pacman -Sl`,
  one cheap local call) → `{name: {v, r, i}}` (version / repo / installed). Descriptions
  come from a single batched `pacman.map_packages(names=…, remote=True)` (`pacman -Si`, local
  sync DB). **No AUR RPC, no network, no per-package info calls** — keeps it I/O-cheap, in
  keeping with the project's I/O-bound caution.

## Design

### Backend — Arch gem (`atlas/gems/arch/controller.py`)

Two small methods (keep the webview layer out of pacman internals):

1. `read_categories() -> Dict[str, List[str]]` — returns `self.categories`; if empty (the
   background `CategoriesDownloader` hasn't populated it yet this session), read & parse the
   cached `CATEGORIES_FILE_PATH` once. Pure/cheap.
2. `list_category_packages(names, limit=150) -> List[ArchPackage]` — given candidate names,
   keep those that exist in the repos (`map_available_packages`), cap at `limit` (sorted),
   fill descriptions from one batched `map_packages(remote=True)`, build `ArchPackage`
   (version/repo/installed/categories) and return. Repo-only by design.

### Backend — webview (`atlas/view/webview/api.py`)

Presentation/normalization lives here:

- `_CATEGORY_BUCKETS` — ordered curated buckets, each `{label, icon, raw:set()}`. Raw→bucket
  mapping merges synonyms (Game+Emulator→Games, Network+Browser+Torrent+P2P+IRC→Internet,
  Audio+Video+AudioVideo→Audio & Video, Development+Python+Javascript→Development,
  System+Settings+Security+Kernel+Printing+Bluetooth+Qt+KDE+Gnome+Xfce+Manjaro→System,
  Graphics+GTK→Graphics, Utility→Utilities, Office→Office).
- `get_categories()` → invert `read_categories()` into buckets, count **distinct** packages
  per bucket, return `[{key, label, icon, count}]` (buckets with 0 packages dropped). Cheap,
  no I/O beyond the (cached) category read.
- `get_category_packages(key)` → bucket key → raw set → names whose categories intersect it
  → `arch_man.list_category_packages(names)` → `_serialize_pkg`. Arch-only (the four
  first-class sources; categories.txt is an Arch index).

### Frontend (`index.html`, `main.js`, `style.css`)

- New sidebar nav item **Browse** (`data-view="browse"`), after Dashboard.
- `activateView('browse')` → `renderBrowse()`: fetch `get_categories`, render a grid of
  `.category-card`s (icon + label + count).
- Click a card → `renderCategoryPackages(key, label)`: a back header (`← Categories`) +
  `get_category_packages(key)` → existing `renderPackages(...)` (reuses cards, collapse,
  install/detail wiring for free).
- Search is cleared on entering Browse (same as other non-search views).

## Tests

`tests/view/webview/test_api.py::BrowseCategoryTest` — stub a manager whose arch gem returns
a fixed `categories` map + `list_category_packages`, assert `get_categories` buckets/counts
and `get_category_packages` serialization + arch-only routing.

## Out of scope (follow-ups)

- AUR/Flatpak/AppImage categories (categories.txt is repo-oriented; would need each gem's own
  category source).
- Sort-within-category (votes/popularity) — overlaps the separate "Sort dropdown" backlog item.
