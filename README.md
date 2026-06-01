# Atlas

**Atlas** is an Arch-focused, all-in-one graphical package manager for Linux. Search,
install, update, downgrade, and remove software from the **official Arch repos, the AUR,
Flatpak, and AppImage** — all from one modern interface.

Atlas is a community fork of [bauh](https://github.com/vinifmor/bauh), rebuilt around a
**[pywebview](https://pywebview.flowrocket.com/) web UI** and a lazy-loaded engine, with
the hot Arch paths moving to **Rust (via PyO3)**.

> Status: actively developed (v0.10.7). Built and tested on Arch / CachyOS.

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

## Install & run (from source)

Atlas needs Python, a system webview (GTK + WebKit), and a Rust toolchain to build the
native `atlas_rs` extension.

```bash
# 1. System prerequisites (Arch)
sudo pacman -S --needed python python-pip gtk3 webkit2gtk python-gobject rust git
#    (use webkit2gtk-4.1 if that's what your distro ships)

# 2. Get the code
git clone https://github.com/Vatteck/atlas.git && cd atlas

# 3. Python env + dependencies
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt setuptools-rust

# 4. Build the Rust extension and install Atlas (editable)
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

Atlas is a **Python** application (`atlas/`) with a **pywebview** front-end
(`atlas/view/webview/`) and one backend "gem" per package type (`atlas/gems/<type>/`).
Slow Arch hot paths are migrating to a **Rust** crate (`rust/`, `atlas_rs`) exposed through
PyO3, behind the existing Python implementations.

Working on Atlas? Start with **[AGENTS.md](AGENTS.md)** (the operating manual) and
**[docs/](docs/)** — `STATUS.md` (current state), `ARCHITECTURE.md`, `ROADMAP.md`,
`DEVELOPMENT.md`, and `atlas_rs-API.md`.

## Roadmap

- Continue moving Arch CPU-bound hot paths to Rust (only where it measurably wins).
- Render rich components (icons, multi-selects) in more dialogs.
- Optional Flatpak/AppImage web links and richer detail panels.
- Re-introduce a non-Qt tray (the legacy Qt tray was removed in the rebrand).
- Advanced container sandboxing ("Vault").

## Credits & license

Atlas is a fork of **[bauh](https://github.com/vinifmor/bauh)** by Vinícius Moreira and
contributors — huge thanks for the foundation. Distributed under the **zlib/libpng**
license; see [LICENSE](LICENSE).

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
