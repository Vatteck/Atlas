# BACKLOG — vision, open work & non-goals

> The longer-horizon planning doc: the **product vision** (north star), the **open menu** we
> pull from, and the **non-goals** we've decided against. STATUS.md is still the live baton
> (what's *in progress* / *just shipped*); this is the forward map. Move an item to a
> `docs/plans/` doc when it gets picked up, and note the outcome in STATUS.md when it ships.

**Last updated:** 2026-06-16 (reconciled shipped items with STATUS; remaining menu is GUI
verification, "Why is this installed?", mirror options, and measurement work.)

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
correctness, stale-render guards, the icon-theme resolver, Flatpak Browse, Attention Center,
transaction previews, Health/`.pacnew`, command palette, and the 0.12 polish/trust work have all
shipped (see Shipped / CHANGELOG / STATUS). What remains, roughly highest-value first:

### Store-quality discovery
- **GUI verification sweep.** Run `atlas --logs` on a real desktop and verify the newest shipped
  surfaces that headless tests cannot fully prove: Browse/AUR buckets, transaction previews,
  PKGBUILD diff annotations, dependency trees, Permissions icons + copyable override toasts,
  Activity export/clear, System Health actions, and mirror command flows. Keep findings in
  `docs/STATUS.md` and move any defects into a focused plan.
- ~~**Dashboard "Attention Center."**~~ ✅ **SHIPPED + GUI-VERIFIED 2026-06-04** — answers "what
  needs my attention today?" with Updates, System safety, Reclaim space, Recent activity, AUR
  safety, and Flatpak permission cards. See [plans/2026-06-04-dashboard-attention-center.md](plans/2026-06-04-dashboard-attention-center.md).
- ~~**Browse 2.0 (Arch polish).**~~ ✅ **SHIPPED 2026-06-05** (needs a GUI eyeball): richer category
  cards (icon + short **description**; no count — repo-only counts mislead), **breadcrumbs**
  (`Browse / <Category>`), **persist last-opened category** (resume chip on the landing), and
  **skeletons** on category pages. *(Sort-within-category + Flatpak-in-bucket already shipped via
  `collapseByName`; Arch/Flatpak/All tabs remain a possible follow-up if the merge proves confusing.)*
  See [plans/2026-06-05-browse-2.0-polish.md](plans/2026-06-05-browse-2.0-polish.md).
- ~~**AUR discovery buckets (not categories).**~~ ✅ **SHIPPED 2026-06-05** — Popular / Recently
  updated / VCS (`-git`) / Binary (`-bin`) buckets in Browse. Data-source decision resolved:
  **precomputed in atlas-files** (a daily GH Action turns `packages-meta-ext-v1.json.gz` into a small
  `arch/aur_discovery.json`; Atlas fetches it, like suggestions/categories). See
  [plans/2026-06-05-aur-discovery-buckets.md](plans/2026-06-05-aur-discovery-buckets.md). Easy to add
  more buckets later (just the generator). Atlas-side work is done; data is pushed and serving from
  atlas-files. *Remaining:* GUI eyeball.
- ~~**Better app detail pages.**~~ ✅ **SHIPPED 2026-06-05** — source-comparison panel, "why this
  source?" hints, dependency summary, and "what will change?" preview shipped as part of the detail
  page / transaction preview work. See [plans/2026-06-05-better-detail-pages.md](plans/2026-06-05-better-detail-pages.md).

### Operation confidence (the trust layer)
- ~~**Universal transaction preview**~~ ✅ **SHIPPED 2026-06-04** — install/update/remove/downgrade,
  Update-All aggregate, and source-comparison/detail-page preview surfaces are implemented. Still needs
  a GUI eyeball for the latest risk-tier and AUR reputation additions.
- ~~**Transaction timeline polish.**~~ ✅ **SHIPPED 2026-06-05** — current-activity line (spinner +
  latest message), collapse/expand raw output, copy-full-log, and a friendly failure summary (auth /
  PGP-keyring / download-404 / conflict / dependency / build). Raw log stays. *(A discrete step
  timeline was dropped — gems don't emit clean phase events.)*
  See [plans/2026-06-05-transaction-timeline.md](plans/2026-06-05-transaction-timeline.md).
- ~~**History / rollback center**~~ ✅ **COMPLETE 2026-06-16** (needs a GUI eyeball): a real
  History/Activity page with filters (action/source/name), date grouping, Downgrade/Reinstall
  rollback affordances, pacman-log links, log clear/export, an automatic Atlas activity-log cap, and
  a per-package activity panel in installed package detail modals. See
  [plans/2026-06-05-history-rollback-center.md](plans/2026-06-05-history-rollback-center.md) and
  [plans/2026-06-16-history-polish.md](plans/2026-06-16-history-polish.md).

### Arch utility cockpit (package-maintenance health only — *not* a YaST)
- ~~**System Health page.**~~ ✅ **shipped 2026-06-04** — Health page with 8 checks (DB-sync age,
  mirrorlist, pacman lock, `.pacnew`, orphans, cache, unused runtimes, AUR chroot), each status +
  one safe action. See [plans/2026-06-04-system-health.md](plans/2026-06-04-system-health.md).
  **Follow-ups ✅ shipped 2026-06-05** (needs a GUI eyeball): keyring freshness + AUR-index-age checks,
  a **gated** "remove stale lock" action (refuses while pacman is running), and a per-check details
  disclosure. *(All "possible follow-ups" done.)*
- ~~**`.pacnew` center.**~~ ✅ **shipped 2026-06-04** — reviewable sub-view with per-file risk badges,
  read-only diff, copy-path, open-pacdiff, regenerate-mirrorlist. No auto-merge. See
  [plans/2026-06-04-pacnew-center-mirror-polish.md](plans/2026-06-04-pacnew-center-mirror-polish.md).
- ~~**Mirror manager polish.**~~ ✅ **shipped 2026-06-04** — Settings → Mirrors shows active-mirror
  summary (count + top hosts + last-modified) + command preview; refreshes after regen (same plan).
  ~~*Follow-up:* country/protocol regenerate options~~ ✅ **shipped 2026-06-07** (needs a GUI eyeball):
  reflector country/protocol(s)/sort pickers with a live command preview, persisted; rate-mirrors keeps
  its fixed command. See [plans/2026-06-07-mirror-regen-options.md](plans/2026-06-07-mirror-regen-options.md).

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
- **"Why is this installed?"** — **mostly ✅ shipped 2026-06-05** as part of the dependency summary:
  explicit-vs-dependency install reason, orphan status, and the required-by list already render on the
  detail page (`get_dependency_summary` + `buildDependencySummaryHTML`). **Remaining delta:** attribute
  a pulled-in dependency to the **explicit package(s)** that dragged it in ("dependency of *X*"), via a
  bounded pure-pacman reverse walk. See [plans/2026-06-17-why-installed.md](plans/2026-06-17-why-installed.md).
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
- ~~**Copy exact command**~~ ✅ **COMPLETE 2026-06-06** (needs a GUI eyeball): a "Copy command" button
  copies the equivalent pacman/makepkg/flatpak command in the **transaction preview** *and* the
  **detail page**, a **reflector** copy in Settings → Mirrors, and — final increment — every Flatpak
  permission edit on the **Permissions page** surfaces the exact `flatpak override --user …` it ran
  (copyable toast). See [plans/2026-06-05-copy-exact-command.md](plans/2026-06-05-copy-exact-command.md).

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
