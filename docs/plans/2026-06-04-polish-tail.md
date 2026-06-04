# 2026-06-04 — Polish / QoL tail (sprint 2)

Working through the three follow-ups parked in `docs/STATUS.md` → **Next**.

---

## 1. Browse beyond Arch-repo → add Flatpak categories

**Goal:** the Browse-by-category view currently only resolves the Arch-repo category index
(`categories.txt`). Extend it so each top-level bucket also lists matching **Flatpak**
(Flathub) apps.

**Feasibility (verified 2026-06-04):**
- **Flatpak: YES.** Flathub exposes `GET /api/v2/collection/category/<Category>?page=&per_page=`
  → `{hits: [...], totalHits: N}`. Each hit carries `app_id` (dotted, correct), `name`,
  `summary`, `icon` (direct URL), `developer_name`, `is_free_license`, `verification_verified`.
  Live counts: Game 721, Network 316, AudioVideo 352, Graphics 219, Development 265,
  Office 240, Utility 720, System 101.
- **AUR: NO.** The AUR RPC v5 (`/rpc/v5/info`) has **no category field** — only freeform
  per-package `Keywords`. There is no category taxonomy to browse. The old pre-4.0 AUR
  categories were dropped years ago. So AUR Browse-by-category has no data source; we
  document this and do not fake it.

**Bucket → Flathub main-category map** (one Flathub category per bucket; subcats like
Audio/Video/Settings fold into their main category):

| bucket       | Flathub category |
|--------------|------------------|
| games        | Game             |
| internet     | Network          |
| multimedia   | AudioVideo       |
| graphics     | Graphics         |
| development  | Development      |
| office       | Office           |
| utilities    | Utility          |
| system       | System           |

**Design:**
- New pure mapper in `atlas/gems/flatpak/flathub.py`: `collection_apps(http_client, category,
  limit, logger)` → list of flat dicts `{id, name, description, icon_url, developer_name,
  is_free, verified}`. One best-effort request; `[]` on error/miss (fail-open, never blocks
  Browse). Add `FLATHUB_CATEGORY_URL`-style call against the existing `FLATHUB_API_URL`.
- New `FlatpakManager.list_category_packages(category, limit)` → `List[FlatpakApplication]`
  built from the mapper output (id/name/version-less/description/icon_url set; `installed=False`).
  Network-cheap: one HTTP call. Skipped entirely when the gem can't work / is disabled.
- `AtlasApi`: add `FLATHUB_CATEGORIES` map on the bucket tuples (extend `CATEGORY_BUCKETS`
  with a 5th element = Flathub category, or `None`). `get_category_packages(key)` now also
  asks the Flatpak gem (if enabled) and **concatenates** Arch + Flatpak serialized pkgs. The
  frontend's existing `collapseByName()` merges same-named multi-source cards for free, and
  `_serialize_pkg` already derives Flathub icons — so **no frontend change** is required.
- `get_categories()` counts stay **Arch-only / cheap** (no per-bucket network call on Browse
  open). Document that the count is "repo packages"; Flatpak apps appear on open.

**Tests:** `test_flathub.py` — `collection_apps` mapping against a captured payload + the
error/empty path. `test_api.py::BrowseCategoryTest` — category packages still return Arch
when Flatpak gem absent; Flatpak results are appended when present (mocked gem).

## 2. Installed-app icons → search the active icon theme (thread-safe, no Gtk.IconTheme)

**Goal:** today `_resolve_installed_icon` only searches `hicolor/*` + `pixmaps`, so
theme-only icons (e.g. `konsole` in Papirus/breeze) fall back to a letter avatar. Broaden
the search to the **active icon theme** and its inheritance chain — without `Gtk.IconTheme`
(not safe off the GTK main thread).

**Design (all filesystem / subprocess, thread-safe):**
- `_active_icon_theme()` — resolve the theme name: `gsettings get org.gnome.desktop.interface
  icon-theme` → `~/.config/gtk-3.0/settings.ini` (`gtk-icon-theme-name`) → `$GTK_THEME` →
  `'hicolor'`. Cached for the session.
- `_theme_icon_dirs(theme)` — for the theme and each theme in its `Inherits=` chain (parsed
  from `index.theme`, across base dirs `~/.local/share/icons`, `~/.icons`,
  `/usr/share/icons`), parse the `index.theme` `Directories=` list and keep the
  Applications-context dirs, ordered scalable-first then by descending `Size`. Returns absolute
  app-icon directories. Cached. Bounded (parse, not a recursive FS walk).
- `_find_icon_file` searches these theme dirs **before** the existing hicolor/pixmaps list, so
  a themed icon wins; the old behaviour remains the fallback. `_ICON_EXTS` unchanged
  (svg/png only — WebKitGTK can't render xpm).

**Tests:** `test_api.py::InstalledIconResolveTest` — extend with a tmp fake theme tree
(index.theme + an apps dir with a named svg) asserting the resolver finds a theme-only icon
and that the inherits chain + scalable-first ordering work.

## 3. Route ad-hoc `Thread(...)` spawns through a shared pool

**Status: deferred (no measured reason).** Golden rule #6 (measure before adding complexity)
and STATUS both flag this as marginal. The controller's `Thread(...)` spawns
(`controller.py:190/250/266/518/669`) are short-lived fan-outs per user action, not a hot
loop; there is no measured contention or thread-exhaustion problem. Converting them to a
shared `ThreadPoolExecutor` adds lifecycle/shutdown surface for no demonstrated win. Leaving
as-is and recording the decision rather than churning the orchestrator.

---

**Verification:** `python -m pytest` green; Browse + icons need a GUI eyeball (network /
theme-dependent, can't be driven headless).
