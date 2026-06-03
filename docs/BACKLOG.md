# BACKLOG — feature & QoL ideas

> Curated wishlist of features/QoL that aren't yet scheduled. STATUS.md is still the live
> baton (what's *in progress* / *just shipped*); this file is the longer-horizon menu we
> pull from. Move an item to a `docs/plans/` doc when it gets picked up, and note the
> outcome in STATUS.md when it ships.

**Last updated:** 2026-06-03

---

## System maintenance (builds on existing orphans + Disk view)

- ~~**Maintenance / Cleanup hub**~~ ✅ **Shipped 2026-06-02** — see
  [plans/2026-06-01-maintenance-hub.md](plans/2026-06-01-maintenance-hub.md). Disk view now
  has a "Reclaim space" panel: orphan packages (checklist), **pacman cache** (`pacman -Sc`,
  freed amount measured before/after), and **unused Flatpak runtimes**
  (`flatpak uninstall --unused`, honouring the configured install level).
- ~~**Downgrade / rollback**~~ ✅ **Shipped 2026-06-02** — see
  [plans/2026-06-02-downgrade-rollback.md](plans/2026-06-02-downgrade-rollback.md). A
  **Downgrade** button in the detail modal (when `can_be_downgraded`) wired to the gems'
  existing `downgrade` via `AtlasApi.downgrade`; the gem picks the target version.

## Arch safety net (distinctive, very Arch-specific)

- ~~**Arch news + `.pacnew` detection**~~ ✅ **Shipped 2026-06-02** — see
  [plans/2026-06-02-arch-safety-net.md](plans/2026-06-02-arch-safety-net.md). A dedicated
  **News** page (archlinux.org feed) and a **`.pacnew`/`.pacsave` notice** on the Updates
  view (detect + list + `pacdiff` guidance, read-only).
  - *Possible follow-ups:* gate/annotate "Update All" with news newer than the last update;
    assist `.pacnew` merging (launch `pacdiff` in a terminal).

## Discovery & detail

- ~~**Rich app detail page**~~ ✅ **Shipped 2026-06-02** — see
  [plans/2026-06-02-rich-app-detail.md](plans/2026-06-02-rich-app-detail.md). The detail
  modal now shows a **screenshot strip** (Flatpak/AppImage) and a **version-history** table
  (installed version highlighted), via newly-wired `get_screenshots`/`get_history`. (The
  description + dependency/required-by metadata were already in the Details table.)
  *Follow-up:* in-modal lightbox instead of opening screenshots in the browser.
- ~~**Browse by category**~~ ✅ **Shipped 2026-06-02** — see
  [plans/2026-06-02-browse-by-category.md](plans/2026-06-02-browse-by-category.md). A new
  **Browse** sidebar page: curated top-level buckets (Games / Internet / Audio & Video /
  Graphics / Development / Office / Utilities / System) built from the shipped
  `categories.txt`; click one to list its repo packages. Arch-only, I/O-cheap (one
  `pacman -Sl` + one batched `pacman -Si`, no AUR/network).
  - *Follow-ups:* sort-within-category (overlaps the Sort dropdown item); AUR/Flatpak
    categories would need each gem's own category source.

## Flatpak transparency & control (a "Flatseal + Flathub-info" theme)

Flatpak is a first-class source; these enrich its detail view + add control. Two linked ideas —
the **safety tier bridges them** (it's *derived* from permissions, not a field). Reality-checked
2026-06-03; all data is reachable (Flathub v2 API — already integrated in `flathub.py` — plus
`flatpak info`/`override` CLI). Flatpak-only; metadata completeness varies (graceful fallback).

- **Rich Flatpak metadata in the detail view** (like Flathub/GNOME Software):
  - **License → Open Source vs Proprietary:** already fetched (`flathub.py` maps `project_license`);
    just classify the SPDX id (FOSS vs proprietary) + show a badge. *Easy.*
  - **Verified developer badge:** Flathub exposes a verification flag (API) — add a fetch. *Easy.*
  - **Age rating (OARS, e.g. "3+"):** `content_rating` is in the AppStream payload we already pull —
    map it. *Easy.*
  - **Downloads/month:** Flathub stats API (`/api/v2/stats/<id>`) — add a fetch. *Easy.*
  - **"Desktop only" / form factor:** from AppStream metadata — fuzzier, optional.
- **Permission management (Flatseal-style):** read perms via `flatpak info --show-permissions <id>`
  (+ static manifest), read/write **user overrides** via `flatpak override --user …` (stored in
  `~/.local/share/flatpak/overrides/`). Backend is easy CLI-wrapping; the work is the UI (a toggle
  grid: filesystem, sockets X11/wayland/network, devices, dbus, env). Value vs Flatseal = integrated,
  no separate app. We read **no** permissions today (`flatpak.py` only runs `flatpak info`).
- **Derived safety tier ("Safe / Probably safe / Potentially unsafe"):** the bridge — GNOME Software
  computes this from the permission set (broad filesystem/device/socket access, no sandbox) +
  proprietary license. Implement as a heuristic over the permissions read above. **Advisory, not a
  verdict** — same framing as the PKGBUILD scanner (never "this is safe/unsafe", just a signal).

## Icons

- ~~**Flatpak icons in search + multi-source best-icon + polished letter fallback**~~ ✅ **Shipped
  2026-06-03.** Flatpak results get the predictable Flathub CDN icon
  (`dl.flathub.org/repo/appstream/x86_64/icons/128x128/<app_id>.png`, lazy-probed, letter on 404);
  multi-source cards borrow any source's icon (fixes Steam); nicer gradient avatar.
- ~~**Installed-app icons from the system**~~ ✅ **Shipped 2026-06-03** — see
  [plans/2026-06-03-installed-app-icons.md](plans/2026-06-03-installed-app-icons.md). `get_pkg_icon`
  resolves an installed package's icon from its `.desktop` `Icon=` (+ name fallback) via a hicolor/
  pixmaps filesystem search, lazy + cached. *Possible follow-up:* broaden beyond hicolor/pixmaps to
  cover theme-specific icons (KDE/breeze, e.g. `konsole`) — would likely need `Gtk.IconTheme`
  (careful re: thread-safety) or scanning the active theme dirs.

## Lighter QoL

- **Keyboard shortcuts** — `/` focuses search, `Esc` closes modals, etc.
- ~~**Sort dropdown**~~ ✅ **Shipped 2026-06-02** — see
  [plans/2026-06-02-sort-dropdown.md](plans/2026-06-02-sort-dropdown.md). Topbar `#sort-filter`:
  Relevance (default) / Votes / Popularity / Recently updated / Name. Client-side, persisted to
  `localStorage`; `last_modified` newly serialized for the "recently updated" mode.
- **Selection toolbar** — now that bulk checkboxes exist, act on N selected packages at
  once (install/remove/update the selection).

## Bigger / exploratory

- **System-tray indicator (non-Qt)** — the legacy Qt tray was removed; a GTK/AppIndicator
  one could return (also on the STATUS.md roadmap).
- **Sandboxed AUR builds ("Vault")** — build AUR packages in a clean chroot
  (`devtools`/`makechrootpkg`, like paru/aurutils) instead of on the host. Design note written:
  [plans/2026-06-02-sandboxed-aur-builds.md](plans/2026-06-02-sandboxed-aur-builds.md) (not yet
  implemented; needs sign-off). Honest scope: isolates the *build* + enforces dep correctness —
  does **not** stop installing a malicious package (install scripts run as root). Pair with
  PKGBUILD review. Atlas builds AUR itself via `makepkg`, so this swaps the build step behind a
  config toggle (strangler-fig). Open question: worth the upkeep vs. lower-effort PKGBUILD-diff review?
