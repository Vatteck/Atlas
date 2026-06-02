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
- **Downgrade / rollback** — pick an older cached version of a package from the pacman
  cache (`/var/cache/pacman/pkg/`). Classic Arch safety move; bauh had it.

## Arch safety net (distinctive, very Arch-specific)

- **Pre-update Arch news check** — pull the archlinux.org news feed and warn *before* a
  large update when there's a "manual intervention required" notice. Prevents broken
  systems; nothing else does this well in a GUI.
- **`.pacnew` / `.pacsave` detection** — after updates pacman leaves config files that need
  merging; surface "N config files need review" with a way to diff/merge.

## Discovery & detail

- **Rich app detail page** — screenshots (`get_screenshots` already exists), full
  description, version/release history, "required by" / dependency list. Pairs with the
  README-screenshots goal; makes Atlas feel like a store.
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
