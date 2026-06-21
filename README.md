# Atlas

[![CI](https://github.com/Vatteck/atlas/actions/workflows/ci.yml/badge.svg)](https://github.com/Vatteck/atlas/actions/workflows/ci.yml)

**Atlas** is an Arch-focused, all-in-one graphical package manager for Linux. Search,
install, update, downgrade, and remove software from the **official Arch repos, the AUR,
Flatpak, and AppImage** — all from one modern interface.

Atlas is a community fork of [bauh](https://github.com/vinifmor/bauh), rebuilt around a
**[pywebview](https://pywebview.flowrocket.com/) web UI** and a lazy-loaded engine.

> Status: actively developed (v0.14.0). Built and tested on Arch / CachyOS.

![Atlas dashboard](docs/screenshots/dashboard.png)

---

## Highlights

- **One card per app, switch the source.** When the same app is available from more than
  one source, Atlas shows a single card with an `Arch | AUR | Flatpak | AppImage` switcher
  — the installed source is marked, and the official repo is preferred over the AUR.
- **Arch and AUR stay distinct.** AUR packages are clearly flagged (it's community-
  maintained and less vetted), ranked by votes, and badged by build type
  (`source` / `binary` / `git`); out-of-date AUR packages are called out.
- **A type filter that actually filters** — instantly narrow results to Arch, AUR,
  Flatpak, or AppImage.
- **Full install flow** — root-password prompt, optional-dependency selection, missing-
  dependency review, and AUR provider choices, all as native HTML dialogs.
- **Settings, in-app** — enable/disable sources, set the Flatpak install level, toggle
  suggestions, notifications, and more.
- **Desktop notifications** when long operations finish.
- **Package web links** — jump to a package's AUR, archlinux.org, or Flathub page.
- **Safe by default** — optional [Timeshift](https://github.com/teejee2008/timeshift)
  snapshot before changes; per-package update pinning.

---

## What's new in 0.14.0

- **Themes.** Pick a theme (Light / Dark / Nord / Solarized Dark / High Contrast) and an accent
  color in Settings → Appearance — applied instantly.
- **~30% faster to first window**, with a brief branded splash while the backend loads.
- **Your preferences persist now** — theme, density, view/sort, and more survive a restart
  (they were silently resetting before).
- **Crisper KDE app icon** (scalable SVG) — no more generic "map" fallback at small sizes.

_Full history in [CHANGELOG.md](CHANGELOG.md)._

## What's new in 0.13.0

- **Update All, your choice of sources.** The Update-All preview now has per-source toggles
  (Arch / AUR / Flatpak / AppImage), so you can run a bulk upgrade while **skipping AUR** —
  handy during the current wave of malicious AUR uploads — without updating one by one. Your
  selection is remembered between runs.
- **Update All no longer stalls** on large update sets — the pre-flight is near-instant
  instead of freezing for minutes, with immediate feedback when you click.

_Full history in [CHANGELOG.md](CHANGELOG.md)._

## What's new in 0.12.0 — the polish-and-trust release

### Dashboard & discovery

- **Attention Center** — the dashboard answers *"what needs my attention today?"* with
  lazy, fail-open cards: Updates, System safety, Reclaim space, Recent activity, AUR safety.
- **Command palette** (`Ctrl+K` / `Ctrl+P`) — fuzzy-filtered launcher to navigate pages
  and run actions, with shortcut badges.
- **Browse 2.0** — richer category cards with icons and descriptions, breadcrumbs, a
  "resume last category" chip, and loading skeletons.
- **AUR discovery buckets** — Popular / Recently-updated / VCS (`-git`) / Binary (`-bin`),
  precomputed daily in `atlas-files`.

### Operation confidence

- **Universal transaction preview** before install, update, uninstall, and downgrade — an
  Update-All aggregate shows per-source split, total download size, and `.pacnew`/news
  warnings. Fail-open, never blocking.
- **Terminal polish** — current-activity line, collapsible/copyable raw log, friendly
  failure summaries (auth / PGP / download / conflict / dependency / build), outcome-colored
  progress bar, and an amber "completed with warnings" state.
- **History / rollback center** — filters, date grouping, Downgrade/Reinstall affordances,
  pacman-log links, log clear/export.
- **Copy exact command** — copy the equivalent `pacman`/`makepkg`/`flatpak`/`reflector`
  command in the preview, the detail page, and on each Permissions edit.

### Better detail pages

- **"Why this source?"** trust hint and **"Why is this installed?"** install-reason banner.
- **Dependency tree view** with lazy drill-down (Requires / Build / Optional / Provides /
  Conflicts / Replaces / Required-by).
- **PKGBUILD viewer** — syntax-highlighted build recipe with risk summary, `.install`
  scriptlet tab, line-linked findings, and a "changed since your build" diff.
- **Source-comparison panel** for apps available from multiple sources.

### Arch maintenance cockpit

- **System Health page** — 8+ checks (DB-sync age, mirrorlist, pacman lock, `.pacnew`,
  orphans, cache, unused runtimes, keyring freshness, AUR-index age), each with a status
  card and one safe action.
- **`.pacnew` center** — per-file risk badges, read-only diff, copy-path, pacdiff launch.
- **Mirror manager** — active-mirror summary and the exact `reflector` regeneration command.
- **Reclaim disk space** — orphan packages, pacman cache, and unused Flatpak runtimes.

### AUR safety

- Heuristic **PKGBUILD scanner** — advisory only, never blocks.
- **Pre-build advisory gate** with diff-since-last-build on updates.
- **Maintainer-changed-hands advisory** for installed AUR packages.
- Opt-in **clean-chroot builds** via `devtools` (`makechrootpkg -I`).

### Flatpak transparency & control

- Detail-modal **badges** — Open Source/Proprietary, Verified/Unverified, downloads, OARS
  age rating — each clickable to an explainer.
- **Permissions list + advisory safety tier** (Safe / Moderate / Potentially unsafe).
- Full **Flatseal-grade Permissions page** (Share / Socket / Device / Features / Filesystem
  / Bus / Environment), via `flatpak override --user`.

### GUI quality

- Display **density modes** (Comfortable / Compact / Dense).
- **Contextual topbar**, unified **empty/error states**, stale-render guards.
- **Grid/list toggle**, **sort dropdown**, keyboard shortcuts, bulk-selection toolbar.
- Rich detail pages with **screenshot lightbox** and **version history**.
- **Non-Qt AppIndicator/SNI tray** — show/hide, update badge, close-to-tray.

### Security

- HTML helpers HTML-escape output before reaching webview-rendered HTML.
- `open_url` validates scheme/host; external links only render for safe HTTP(S) URLs.

---

## Screenshots

| One app, every source | Full package details |
|:---:|:---:|
| [![Source switcher](docs/screenshots/apppanel.png)](docs/screenshots/apppanel.png) | [![Package details](docs/screenshots/details.png)](docs/screenshots/details.png) |
| **Reclaim disk space** | **Live transaction output** |
| [![Disk view](docs/screenshots/diskpage.png)](docs/screenshots/diskpage.png) | [![Install terminal](docs/screenshots/terminal.png)](docs/screenshots/terminal.png) |

## Supported sources

| Source | Default | Notes |
|--------|:------:|-------|
| **Arch official repos** | ✅ on | via `pacman` |
| **AUR** | ✅ on | builds, conflict/dependency handling, multi-threaded downloads |
| **Flatpak** | ✅ on | install/update/remove, system or user level |
| **AppImage** | ✅ on | integrated, from AppImageHub |
| Snap | ⬜ off | available but disabled by default (Ubuntu-centric) |
| Debian (dpkg/apt) | ⬜ off | available but disabled by default |
| Native Web apps | ⬜ off | Electron/Nativefier; disabled by default |

Snap, Debian, and Web are kept for completeness but are off by default on this Arch-focused
build. Re-enable any of them under **Settings → Package types**.

## Install (Arch package)

The easiest way on Arch: install from the AUR:

```bash
yay -S atlas-pm-git
atlas             # launch
```

Or build locally from the PKGBUILD at [`linux_dist/arch/PKGBUILD`](linux_dist/arch/PKGBUILD):

```bash
git clone https://github.com/Vatteck/atlas.git
cd atlas/linux_dist/arch
makepkg -si       # builds and installs; pulls deps from the official repos
atlas             # launch
```

## Install & run (from source)

Atlas needs Python and a system webview (GTK + WebKit):

```bash
# 1. System prerequisites (Arch)
sudo pacman -S --needed python python-pip gtk3 webkit2gtk python-gobject git
#    (use webkit2gtk-4.1 if that's what your distro ships)

# 2. Get the code
git clone https://github.com/Vatteck/atlas.git && cd atlas

# 3. Python env + dependencies
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 4. Install Atlas (editable)
pip install -e .

# 5. Run
atlas            # GUI   (or: python -m atlas.app)
atlas --logs     # GUI with logging
atlas-cli        # CLI
```

## Files, cache, and logs

- `~/.config/atlaspm` (or `/etc/atlaspm` for **root**) — configuration
- `~/.cache/atlaspm` (or `/var/cache/atlaspm` for **root**) — installed-app data, databases,
  indexes, and the activity log
- `/tmp/atlaspm@$USER` — temporary build/working files

Suggestion and category data is fetched at runtime from
[Vatteck/atlas-files](https://github.com/Vatteck/atlas-files).

## Architecture

Atlas is a **pure-Python** application (`atlas/`) with a **pywebview** front-end
(`atlas/view/webview/`) and one backend "gem" per package type (`atlas/gems/<type>/`).
Each gem wraps a system package manager (pacman, AUR, Flatpak, AppImage).

Working on Atlas? Start with **[AGENTS.md](AGENTS.md)** (the operating manual) and
**[docs/](docs/)** — `STATUS.md` (current state), `ARCHITECTURE.md`, `ROADMAP.md`,
`DEVELOPMENT.md`.

## Roadmap

The big transitions are done: Qt5 → pywebview UI, and back to a clean **pure-Python**
engine after the Rust hot-paths experiment was measured and dropped. The major product
themes have also shipped: rich details/screenshots, Browse, system tray, AUR safety,
clean-chroot AUR builds, Flatpak transparency, Flatseal-grade permission controls,
the Attention Center dashboard, universal transaction preview, the Arch maintenance
cockpit (System Health + `.pacnew` center + mirrors), the PKGBUILD viewer, command palette,
history/rollback center, copy-exact-command, and the security pass.

See [`CHANGELOG.md`](CHANGELOG.md) for the full release history,
[`docs/STATUS.md`](docs/STATUS.md) for the live handoff baton, and
[`docs/BACKLOG.md`](docs/BACKLOG.md) for the longer-horizon menu.

## Credits & license

Atlas is a fork of **[bauh](https://github.com/vinifmor/bauh)** by Vinícius Moreira and
contributors — huge thanks for the foundation. Distributed under the **zlib/libpng**
license; see [LICENSE](LICENSE).

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
