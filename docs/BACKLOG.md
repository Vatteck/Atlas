# BACKLOG — vision, open work & non-goals

> The longer-horizon planning doc: the **product vision** (north star), the **open menu** we
> pull from, and the **non-goals** we've decided against. STATUS.md is still the live baton
> (what's *in progress* / *just shipped*); this is the forward map. Move an item to a
> `docs/plans/` doc when it gets picked up, and note the outcome in STATUS.md when it ships.

**Last updated:** 2026-06-04 (folded the polish/QoL roadmap in — vision + open work + non-goals;
the former `hroadmap.md` was absorbed here and deleted. Its P0 had already shipped.)

---

## North star (product vision)

Atlas should feel like:

> **GNOME Software / Discover polish + paru/yay Arch awareness + Flatseal permissions +
> BleachBit-style cleanup + an Arch news/`.pacnew` safety cockpit** — in one app.

Not "another package-manager GUI." The angle is a **beautiful GUI for Arch users who still
want to know what the hell is happening.** The personality we're aiming for:

- Pretty enough for GUI people; honest enough for Arch people.
- Safer than Pamac-style "click update and pray" — surfaces the scary parts instead of hiding
  them under pastel.
- More Arch-aware than Discover/GNOME Software; less ugly than Octopi.
- More integrated than hand-stitching `paru` + Flatseal + `pacdiff` + `reflector` + cache
  cleanup.

The win condition: **make dangerous Arch maintenance feel calm, visual, and reversible without
hiding the danger.** Every system-mutating action should feel controlled and explained.

---

## Open work (the forward menu)

Folded from the polish/QoL roadmap. Its **P0 ("finish what shipped") is already done** — Browse
correctness, stale-render guards, the GUI-verification pass, the icon-theme resolver, and Flatpak
Browse all shipped in sprints 1–2 (see Shipped / CHANGELOG). What remains, roughly highest-value
first:

### Store-quality discovery
- **Dashboard "Attention Center."** Make the dashboard answer *"what needs my attention today?"*
  Lazy/best-effort cards (fail-open, skeletons OK, never block startup): **Updates** (count +
  Arch/AUR/Flatpak split + "news before upgrade?"), **System safety** (`.pacnew` count, DB-sync
  age, pacman lock), **Reclaim space** (orphans, cache estimate, unused runtimes), **Recent
  activity**, **AUR safety** (chroot/devtools status), **Flatpak permissions** (risky-app count →
  Permissions page). Most backends already exist; mainly a compact `AtlasApi.get_dashboard_summary`
  + UI.
- **Browse 2.0 (Arch polish).** Richer category cards (icon + count + short description),
  breadcrumbs, persist last-opened category, better category-page skeletons. *(Sort-within-category
  and Flatpak-in-bucket already shipped; Flatpak landed merged into buckets via `collapseByName`,
  not as Arch/Flatpak/All tabs — tabs are still an option if the merge proves confusing.)*
- ~~**AUR discovery buckets (not categories).**~~ ✅ **SHIPPED 2026-06-05** — Popular / Recently
  updated / VCS (`-git`) / Binary (`-bin`) buckets in Browse. Data-source decision resolved:
  **precomputed in atlas-files** (a daily GH Action turns `packages-meta-ext-v1.json.gz` into a small
  `arch/aur_discovery.json`; Atlas fetches it, like suggestions/categories). See
  [plans/2026-06-05-aur-discovery-buckets.md](plans/2026-06-05-aur-discovery-buckets.md). Easy to add
  more buckets later (just the generator). *Remaining:* push the atlas-files commit + enable the Action.
- **Better app detail pages.** A **source-comparison panel** (Arch vs AUR vs Flatpak vs AppImage:
  version, size, maintainer/publisher, trust badges, update availability), **"why this source?"**
  hints (vetted repo / community AUR build / verified vs community Flatpak), a **dependency summary**
  (direct / optional / required-by counts), and a **"what will change?"** preview. High value
  because Atlas is multi-source and most GUIs explain source tradeoffs badly.

### Operation confidence (the trust layer)
- **Universal transaction preview** before install/update/remove/downgrade — cards/badges/
  accordions, *not* a wall of text. Installs: pkgs/source/version/new-deps/optdeps/estimate/AUR
  warnings/Flatpak-perms. Updates: current→new, source split, AUR maintainer change?, PKGBUILD diff?,
  Arch news newer than sync?, `.pacnew` present? Uninstall: will-remove + reverse-dep warnings +
  orphan candidates.
- ~~**Transaction timeline polish.**~~ ✅ **SHIPPED 2026-06-05** — current-activity line (spinner +
  latest message), collapse/expand raw output, copy-full-log, and a friendly failure summary (auth /
  PGP-keyring / download-404 / conflict / dependency / build). Raw log stays. *(A discrete step
  timeline was dropped — gems don't emit clean phase events.)*
  See [plans/2026-06-05-transaction-timeline.md](plans/2026-06-05-transaction-timeline.md).
- **History / rollback center.** Wrap the existing downgrade in a real History/Activity page:
  timeline of installs/updates/removals, filter by package/source/action, a per-package History tab,
  "downgrade available" / "reinstall previous version" affordances, pacman-log links.

### Arch utility cockpit (package-maintenance health only — *not* a YaST)
- ~~**System Health page.**~~ ✅ **shipped 2026-06-04** — Health page with 8 checks (DB-sync age,
  mirrorlist, pacman lock, `.pacnew`, orphans, cache, unused runtimes, AUR chroot), each status +
  one safe action. See [plans/2026-06-04-system-health.md](plans/2026-06-04-system-health.md).
  *Possible follow-ups:* keyring freshness, AUR-index age, a gated "remove stale lock" action, and a
  per-check details disclosure.
- ~~**`.pacnew` center.**~~ ✅ **shipped 2026-06-04** — reviewable sub-view with per-file risk badges,
  read-only diff, copy-path, open-pacdiff, regenerate-mirrorlist. No auto-merge. See
  [plans/2026-06-04-pacnew-center-mirror-polish.md](plans/2026-06-04-pacnew-center-mirror-polish.md).
- ~~**Mirror manager polish.**~~ ✅ **shipped 2026-06-04** — Settings → Mirrors shows active-mirror
  summary (count + top hosts + last-modified) + command preview; refreshes after regen (same plan).
  *Possible follow-ups:* country/protocol regenerate options.

### GUI polish (low backend, high perceived quality)
- ~~**Command palette** (`Ctrl+K`/`Ctrl+P`)~~ ✅ **shipped + GUI-verified 2026-06-04** — fuzzy-filtered
  launcher: navigate to any page + run actions (update all, clean orphans, refresh, grid/list, select,
  regenerate mirrors, pacdiff, export, focus search); shortcut `<kbd>` badges. See
  [plans/2026-06-04-command-palette.md](plans/2026-06-04-command-palette.md).
- ~~**Density / layout modes**~~ ✅ **shipped 2026-06-04** — Comfortable/Compact/Dense via a
  `body.density-*` class, Settings → General (instant, localStorage). See
  [plans/2026-06-04-gui-polish-small.md](plans/2026-06-04-gui-polish-small.md).
- ~~**Contextual topbar**~~ ✅ **shipped 2026-06-04** — package-list controls show only where they
  apply (same plan). Breadcrumbs are still a possible follow-up.
- ~~**Finish empty/error/loading states**~~ ✅ **shipped 2026-06-04** — unified `emptyStateHTML`
  across News / categories / category-packages / Permissions / Activity (same plan). *(In-modal
  screenshots/history intentionally just hide; a couple of deeper states could still be tailored.)*
- ~~**Extend stale-render guards**~~ ✅ **shipped 2026-06-04** — a `navEpoch` + delayed-spinner
  pattern now guards every async utility renderer (News/Permissions/Settings/Activity/Disk/Browse/
  Health/pacnew): last-clicked wins and rapid switching no longer flashes intermediate pages.

### Power-user sugar (make it beautiful)
- **"Why is this installed?"** — explicit vs dependency, required-by list, orphan status, reverse
  deps.
- ~~**Dependency tree view**~~ ✅ **SHIPPED 2026-06-05** (needs a GUI eyeball): the detail-page
  Dependencies section now shows Requires / Optional / Build / Provides / Conflicts / Replaces /
  Required-by as accordion groups, with **Requires + Build as drill-down trees** (expand a dep → its
  requires load lazily, one cheap level per click). See
  [plans/2026-06-05-dependency-tree-view.md](plans/2026-06-05-dependency-tree-view.md).
- ~~**PKGBUILD viewer as a first-class UI**~~ ✅ **COMPLETE 2026-06-05** (needs a GUI eyeball):
  reachable from the **AUR detail page** ("Build recipe → View PKGBUILD") *and* the **install
  transaction preview**; a dedicated viewer with a sticky combined risk summary, maintainer/source/
  checksums panel, line-linked findings, the full syntax-highlighted line-numbered PKGBUILD, a
  **`.install` scriptlet tab**, a **copy** button, and a **"changed since your build" diff tab** (for
  installed AUR pkgs whose built commit we cached). See
  [plans/2026-06-05-pkgbuild-viewer.md](plans/2026-06-05-pkgbuild-viewer.md).
- **Copy exact command** — "copy equivalent install/update/Flatpak-override/reflector command." GUI
  stays primary, nothing feels hidden.

---

## Non-goals — don't build (yet)

These sound tempting and are traps. They also re-derive the AGENTS.md §3 guardrails.

- **AI package recommendations.** Easy to make cringe, slow, and untrustworthy. If ever: local,
  optional, framed as *"explain package metadata,"* never *"AI decides what to install."*
- **A full system control center (YaST).** Atlas is package/system-**maintenance** focused — mirrors,
  `.pacnew`, cache, runtimes, permissions, AUR build health. Not users/services/kernel/display/
  network/bluetooth. Keep the boundary.
- **Automatic `.pacnew` merging.** Show diffs, launch `pacdiff`, warn — never invent config-merge
  magic (that's how you get angry Arch users with broken boots).
- **Reintroducing Rust or Qt.** Not for polish, not for "performance vibes." Measure a CPU-bound hot
  path with a small result and get sign-off, or don't. (AGENTS.md §3.2 + ROADMAP.)
- **AUR categories pretending to be accurate.** The data is messy; use curated discovery buckets
  (above), not fake taxonomy.

---

## Shipped (history)

Everything below has shipped — kept as a themed index with plan-doc links. The authoritative
record is `CHANGELOG.md` (0.11.0) + the STATUS.md Done log.

### System maintenance
- ~~**Maintenance / Cleanup hub**~~ ✅ **2026-06-02** —
  [plans/2026-06-01-maintenance-hub.md](plans/2026-06-01-maintenance-hub.md). Disk-view "Reclaim
  space": orphans (checklist), pacman cache (`pacman -Sc`, freed amount measured), unused Flatpak
  runtimes.
- ~~**Downgrade / rollback**~~ ✅ **2026-06-02** —
  [plans/2026-06-02-downgrade-rollback.md](plans/2026-06-02-downgrade-rollback.md). Detail-modal
  **Downgrade** button → `AtlasApi.downgrade`; the gem picks the target version.

### Arch safety net
- ~~**Arch news + `.pacnew` detection**~~ ✅ **2026-06-02** —
  [plans/2026-06-02-arch-safety-net.md](plans/2026-06-02-arch-safety-net.md). **News** page +
  `.pacnew`/`.pacsave` notice. Follow-ups also shipped: **Update-All news gate** and **`.pacnew`
  pacdiff/mirrorlist assist** (these feed the open "System Health" / "`.pacnew` center" items above).

### Discovery & detail
- ~~**Rich app detail page**~~ ✅ **2026-06-02** —
  [plans/2026-06-02-rich-app-detail.md](plans/2026-06-02-rich-app-detail.md). Screenshot strip +
  version history; in-modal lightbox followed.
- ~~**Browse by category**~~ ✅ **2026-06-02** —
  [plans/2026-06-02-browse-by-category.md](plans/2026-06-02-browse-by-category.md). Curated buckets
  from `categories.txt`. Follow-ups: sort-within-category ✅ (sprint 1); **Flatpak categories** ✅
  **2026-06-04** ([plans/2026-06-04-polish-tail.md](plans/2026-06-04-polish-tail.md)). AUR categories
  are **infeasible** (no taxonomy) → see "AUR discovery buckets" in Open work instead.

### Flatpak transparency & control
- **Mostly ✅ 2026-06-03.** Detail badges (Open Source/Proprietary, Verified/Unverified,
  downloads/month, OARS age rating, form factor), permissions list + advisory safety tier, in-modal
  override editing, and the full Flatseal-grade **Permissions page**
  ([plans/2026-06-03-flatpak-permissions-page.md](plans/2026-06-03-flatpak-permissions-page.md)):
  Share/Socket/Device/Features/Filesystem/Bus/Environment, tabbed, via `flatpak override --user`.
  *Persist deferred* (no negative flag for `--persist`).

### Icons
- ~~**Flatpak/multi-source/letter-avatar icons**~~ ✅ **2026-06-03**, ~~**installed-app icons from
  the system**~~ ✅ **2026-06-03** ([plans/2026-06-03-installed-app-icons.md](plans/2026-06-03-installed-app-icons.md)),
  and ~~**active-icon-theme resolution**~~ ✅ **2026-06-04**
  ([plans/2026-06-04-polish-tail.md](plans/2026-06-04-polish-tail.md), theme + `Inherits` chain, no
  `Gtk.IconTheme`).

### Lighter QoL
- ~~**Keyboard shortcuts**~~ ✅ (`/` search, `Esc` close, help button), ~~**Sort dropdown**~~ ✅
  **2026-06-02** ([plans/2026-06-02-sort-dropdown.md](plans/2026-06-02-sort-dropdown.md)),
  ~~**Selection toolbar**~~ ✅ (`batch_install`/`batch_uninstall`).

### Bigger / exploratory
- ~~**System-tray indicator (non-Qt)**~~ ✅ AppIndicator/SNI tray (icon, show/hide, quit, update
  badge) + Settings toggle.
- ~~**Sandboxed AUR builds**~~ ✅ **& GUI-verified 2026-06-03** —
  [plans/2026-06-02-sandboxed-aur-builds.md](plans/2026-06-02-sandboxed-aur-builds.md). Opt-in clean-
  chroot building (`makechrootpkg`) with `-I` dep injection + host-build fallback. Isolates the
  *build*, not a malicious package.
