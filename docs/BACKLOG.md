# BACKLOG — feature & QoL ideas

> Curated wishlist of features/QoL that aren't yet scheduled. STATUS.md is still the live
> baton (what's *in progress* / *just shipped*); this file is the longer-horizon menu we
> pull from. Move an item to a `docs/plans/` doc when it gets picked up, and note the
> outcome in STATUS.md when it ships.

**Last updated:** 2026-06-01

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
- **Browse by category** — the `atlas-files` repo already ships category data; a store-like
  "Games / Dev / Graphics" browse view can use it.

## Lighter QoL

- **Keyboard shortcuts** — `/` focuses search, `Esc` closes modals, etc.
- **Sort dropdown** — votes / popularity / recently-updated.
- **Selection toolbar** — now that bulk checkboxes exist, act on N selected packages at
  once (install/remove/update the selection).

## Bigger / exploratory

- **System-tray indicator (non-Qt)** — the legacy Qt tray was removed; a GTK/AppIndicator
  one could return (also on the STATUS.md roadmap).
- **Container sandboxing ("Vault")** — aspirational, no design yet.
