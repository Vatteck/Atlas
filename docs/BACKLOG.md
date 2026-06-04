# BACKLOG — feature & QoL ideas

> Curated wishlist of features/QoL that aren't yet scheduled. STATUS.md is still the live
> baton (what's *in progress* / *just shipped*); this file is the longer-horizon menu we
> pull from. Move an item to a `docs/plans/` doc when it gets picked up, and note the
> outcome in STATUS.md when it ships.

**Last updated:** 2026-06-03 (reconciled — Flatpak permissions page, chroot builds, shortcuts, selection toolbar all shipped)

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

**Mostly ✅ shipped 2026-06-03.** Detail-modal badges: **Open Source / Proprietary** (`is_free_license`),
**Verified / Unverified** (Flathub verification metadata), **downloads/month** (`/api/v2/stats`) — all
clickable to explainer popups. **Permissions list + advisory safety tier** (Safe / Moderate /
Potentially unsafe, derived from the permission set + license — *advisory, not a verdict*). **Override
editing**: in-modal quick toggles **and** the full Flatseal-grade **Permissions page** (see the
shipped item above). Backend in `flathub.py`/`permissions.py`/`flatpak.py`.

- **Still open (small):** **OARS age rating** badge — `content_rating` is already in the AppStream
  payload we pull; just map it (e.g. "3+"). *Easy.* And an optional **"desktop only" / form-factor**
  hint from AppStream metadata (fuzzier, optional).

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

## Flatpak (follow-ups to the transparency & control theme)

- ~~**Dedicated Flatseal-grade Permissions page (sidebar)**~~ ✅ **Shipped 2026-06-03** — see
  [plans/2026-06-03-flatpak-permissions-page.md](plans/2026-06-03-flatpak-permissions-page.md).
  Sidebar **Permissions** page, master/detail (installed-Flatpak list → grouped sandbox), iOS-style
  switches, `flag=value` sub-labels, per-app Reset. All increments done: (1) static toggles
  Share/Socket/Device/Features, (2) Filesystem (preset dir toggles + ro/rw/create modes +
  custom-path add/remove), (3) Bus (session/system talk/own) + Environment add/remove. Categories
  are **tabbed**. All via `flatpak override --user` (no root). *Persist deferred:* `flatpak override`
  has no negative flag for `--persist`, so clean removal would need override-keyfile editing.

## Lighter QoL

- ~~**Keyboard shortcuts**~~ ✅ **Shipped** — `/` focuses search, `Esc` closes modals/popups, plus a
  shortcuts-help button (`#shortcuts-help-btn`). Global `keydown` handler in `main.js`.
- ~~**Sort dropdown**~~ ✅ **Shipped 2026-06-02** — see
  [plans/2026-06-02-sort-dropdown.md](plans/2026-06-02-sort-dropdown.md). Topbar `#sort-filter`:
  Relevance (default) / Votes / Popularity / Recently updated / Name. Client-side, persisted to
  `localStorage`; `last_modified` newly serialized for the "recently updated" mode.
- ~~**Selection toolbar**~~ ✅ **Shipped** — bulk checkboxes + a batch action bar
  (`AtlasApi.batch_install`/`batch_uninstall`) act on N selected packages at once.

## Bigger / exploratory

- ~~**System-tray indicator (non-Qt)**~~ ✅ **Shipped** — AppIndicator/SNI tray (icon, show/hide,
  quit, update-count badge) + a Settings toggle.
- ~~**Sandboxed AUR builds ("Vault")**~~ ✅ **Shipped & GUI-verified 2026-06-03** — see
  [plans/2026-06-02-sandboxed-aur-builds.md](plans/2026-06-02-sandboxed-aur-builds.md). Opt-in
  (`aur_build_chroot`, off by default; Settings toggle) clean-chroot building via `devtools`
  (`makechrootpkg`/`mkarchroot`/`arch-nspawn`), with **`-I` injection** of already-built AUR deps and
  a **host-build fallback** when devtools is absent/setup fails. Honest scope kept: isolates the
  *build*, not a malicious package. Verified end-to-end installing `protonup-qt` (its AUR deps
  injected into the chroot copy).
