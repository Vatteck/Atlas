# Installed-app icons from the system (icon theme / .desktop) — 2026-06-03

> **Status: implemented (2026-06-03).** `AtlasApi.get_pkg_icon` + helpers; frontend `data-pkgicon`
> lazy-resolve. Live-verified: steam→PNG, firefox→SVG. Known limits: only **SVG/PNG** (XPM can't
> render in WebKitGTK → skipped → avatar); only **hicolor + pixmaps** dirs searched (no
> `Gtk.IconTheme`, for thread-safety), so theme-specific icons (e.g. KDE/breeze, like `konsole`)
> aren't found → avatar. Both are graceful (no broken images, no regression).
>
> Layer 4 of the icon work (1–3 shipped in `b69de0d`). Gives *installed* Arch/AUR/repo apps a real
> icon (search/non-installed packages have no icon source anywhere → keep the letter avatar).

## Approach (lazy + cached; no GTK → thread-safe)

A new backend method `AtlasApi.get_pkg_icon(pkg_id)` resolves an installed package's icon on demand
(only for cards actually scrolled into view), and the frontend swaps it in — mirroring the existing
remote-icon lazy-loader.

Resolution for an installed package `name`:
1. **`.desktop` `Icon=`** (accurate): `pacman -Ql <name>` → the package's `*.desktop` files under
   `/…/applications/` → parse `Icon=`.
2. **Fallback: icon named after the package** (catches the common case).
3. For each candidate icon name, find a file in the standard locations
   (`/usr/share/icons/hicolor/<size>/apps/<name>.{svg,png}`, `/usr/share/pixmaps/<name>.{svg,png,xpm}`)
   — a plain filesystem search (no `Gtk.IconTheme`, which isn't thread-safe off the GTK main thread).
4. Base64-embed via the existing `_get_valid_icon_url(path)` → a `data:` URI.

Results cached per `pkg_id` (in-memory). Returns `''` when nothing resolves (→ letter avatar stays).

## Frontend

- Card: when a package is **installed and has no icon_url**, stamp `data-pkgicon="<pkg_id>"` on the
  `<img>`.
- The existing IntersectionObserver (`deferredIconLoad`) also handles `data-pkgicon`: on view, call
  `get_pkg_icon(id)` and set `img.src` if a data URI comes back (silent no-op otherwise).

## Scope / caveats

- Installed packages only (non-installed search results have no local icon → letter avatar — inherent).
- `pacman -Ql` is one subprocess per resolved package, but lazy + cached keeps it cheap.
- Prefer SVG / mid-size raster to keep data URIs small.
- Tests: pure `Icon=` parser + filename search (temp dir) + `get_pkg_icon` contract (non-installed → '').
