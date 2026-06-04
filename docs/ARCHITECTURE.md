# Atlas Architecture

Atlas is an **Arch-focused graphical package manager** for Linux. It is a fork of
[bauh](https://github.com/vinifmor/bauh), rebuilt around a **pywebview** front-end and
kept intentionally **pure Python**.

The first-class sources are:

- **Arch official repositories**
- **AUR**
- **Flatpak**
- **AppImage**

Snap, Debian, and native Web apps still exist as optional gems, but they are disabled by
default in the Arch-focused build.

Two earlier transitions are complete and should be treated as closed:

- **Qt5 was removed.** The active UI is the pywebview/WebKitGTK interface under
  `atlas/view/webview/`. Do not reintroduce Qt without explicit project sign-off.
- **The Rust `atlas_rs` experiment was removed.** Atlas is I/O-bound around pacman, AUR,
  Flatpak, network, and build tools. Native code did not earn the toolchain and dual-
  implementation cost. Keep the lesson, not the extension: only add native code for a
  measured CPU-bound hot path with a small result, and only after sign-off.

For current work, read [STATUS.md](./STATUS.md). For the historical Rust verdict, read
[ROADMAP.md](./ROADMAP.md). For build and test commands, read [DEVELOPMENT.md](./DEVELOPMENT.md).

---

## 1. Bird's-eye view

```text
                        ┌──────────────────────────────────────────┐
                        │            pywebview window              │
                        │   index.html · main.js · style.css       │  ← Front-end
                        └───────────────────┬──────────────────────┘
                                            │  JS ↔ Python bridge
                        ┌───────────────────▼──────────────────────┐
                        │        atlas/view/webview/api.py          │
                        │              AtlasApi                     │  ← View/API layer
                        └───────────────────┬──────────────────────┘
                                            │  Python calls
                        ┌───────────────────▼──────────────────────┐
                        │   atlas/view/core/controller.py           │
                        │      GenericSoftwareManager               │  ← Orchestration
                        └───────────────────┬──────────────────────┘
            ┌───────────────┬───────────────┼───────────────┬───────────────┐
            ▼               ▼               ▼               ▼               ▼
       ┌─────────┐    ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
       │  arch   │    │ flatpak │     │appimage │     │  snap   │     │ web /   │
       │  gem    │    │  gem    │     │  gem    │     │  gem    │     │ debian  │
       └─────────┘    └─────────┘     └─────────┘     └─────────┘     └─────────┘
```

Each gem implements the `SoftwareManager` abstract base class
(`atlas/api/abstract/controller.py`). `GenericSoftwareManager` owns the enabled managers,
prepares them lazily, and routes each operation to the backend that owns the package type.

---

## 2. Main layers

### 2.1 Front-end — `atlas/view/webview/`

- `index.html`, `main.js`, and `style.css` render the UI inside WebKitGTK via pywebview.
- The JS side calls Python through the pywebview bridge bound to `AtlasApi`.
- Dialogs are **HTML modals**, not native browser dialogs. WebKitGTK does not provide
  reliable `window.prompt`, `window.confirm`, or `window.alert` here.
- Supporting modules:
  - `activity_log.py` — transaction/activity history helpers.
  - `watcher.py` — progress, confirmations, password prompts, and terminal output flow.
  - `export.py` — export helpers.

### 2.2 View/API bridge — `atlas/view/webview/api.py`

`AtlasApi` is the only surface the front-end should call directly. It translates UI
intents into manager operations, serializes package objects for JS, exposes app settings,
and starts long-running work without blocking the UI.

Common responsibilities:

- Search/read installed/read updates.
- Install, update, uninstall, downgrade, and launch operations.
- Settings read/write through the webview-native settings page.
- Arch safety helpers: news, `.pacnew`, mirror regeneration, PKGBUILD review flow.
- Flatpak metadata and permission override APIs.
- Tray/settings integration.

### 2.3 Orchestration — `atlas/view/core/controller.py`

`GenericSoftwareManager` owns the collection of gem managers and routes operations. It is
responsible for:

- Keeping enabled package sources separated.
- Preparing managers lazily instead of booting every backend eagerly at startup.
- Fan-out/fan-in operations across gems where the UI needs a unified result.
- Preserving source identity so Arch official packages and AUR packages do not blur
  together.

### 2.4 Gems — `atlas/gems/<type>/`

Each gem is a backend for one package source. The Arch gem is the heaviest because it has
to cover pacman, AUR RPC, build flows, dependencies, update planning, and safety checks.

| Area | Main files | Notes |
|---|---|---|
| Arch/AUR | `atlas/gems/arch/controller.py`, `pacman.py`, `updates.py`, `dependencies.py`, `aur.py`, `pkgbuild_audit.py`, `chroot.py` | Official repo + AUR management, PKGBUILD review, maintainer advisory, optional clean-chroot builds. |
| Flatpak | `atlas/gems/flatpak/controller.py`, `flatpak.py`, `flathub.py`, `permissions.py` | Flathub metadata, install/update/remove, safety/permission display, override editing. |
| AppImage | `atlas/gems/appimage/` | AppImage discovery/integration. |
| Snap | `atlas/gems/snap/` | Optional, disabled by default. |
| Debian | `atlas/gems/debian/` | Optional, disabled by default. |
| Web apps | `atlas/gems/web/` | Optional native-web-app support, disabled by default. |

---

## 3. Current product flows

### 3.1 Search and multi-source cards

The UI can group multiple package sources into one app card. The source switcher keeps the
available package types visible while preserving which source is installed and which source
is safer/preferred. Arch official packages and AUR packages must stay visibly distinct.

### 3.2 AUR safety

AUR support is deliberately advisory instead of pretending to prove safety. Current layers
include:

- Heuristic PKGBUILD and `.install` scanner.
- Advisory pre-build confirmation gate.
- Diff-since-last-build on updates.
- Maintainer-changed-hands advisory for installed AUR packages with a cached baseline.
- Optional clean-chroot builds through Arch `devtools`, with built AUR dependencies
  injected using `makechrootpkg -I`.

The chroot path isolates the build environment. It does **not** make a malicious package
safe after installation; do not describe it that way.

### 3.3 Flatpak transparency and control

Flatpak support surfaces Flathub/AppStream metadata and lets users inspect and edit
sandbox overrides:

- Open-source/proprietary badge.
- Verified/unverified publisher badge.
- Download/size/form-factor/OARS-style metadata where available.
- Advisory safety tier based on permissions and license metadata.
- In-detail permission popups.
- Dedicated Permissions page with grouped Share, Socket, Device, Features, Filesystem,
  Bus, and Environment controls.

Overrides are applied with `flatpak override --user` and generally take effect on next app
launch.

### 3.4 System tray

The tray is integrated into normal `atlas` startup and is optional/additive. It uses
AyatanaAppIndicator3 or AppIndicator3 to publish a StatusNotifierItem. Missing typelibs or
`ui.tray.enabled: false` simply skip tray setup.

The tray supports show/hide, quit, update-count polling, and an optional close-to-tray
behavior. KDE requires a rendered badge icon rather than relying on `set_label`, so tray
icon updates are handled in `atlas/view/tray.py`.

---

## 4. Application entry points

Defined in `pyproject.toml` and `setup.py`:

| Command | Target | Purpose |
|---|---|---|
| `atlas` | `atlas.app:main` | Launch the GUI. |
| `atlas-cli` | `atlas.cli.app:main` | Command-line interface. |

`atlas/app.py:main` builds the gem managers, wraps them in `GenericSoftwareManager`, binds
an `AtlasApi`, optionally starts the tray integration, and opens the pywebview window at
`atlas/view/webview/index.html`.

---

## 5. Runtime layout

| Path | Contents |
|---|---|
| `~/.config/atlaspm` (`/etc/atlaspm` as root) | Configuration (`config.yml`, gem configs). |
| `~/.cache/atlaspm` (`/var/cache/atlaspm` as root) | Installed-app data, AUR index, databases, activity data. |
| `/tmp/atlaspm@$USER` | Logs and temporary files. |

Runtime metadata such as suggestions, categories, AppImage data, and web-app environment
files is fetched from the separate `Vatteck/atlas-files` repository on its `main` branch.

---

## 6. Source tree quick reference

```text
atlas/
├── app.py                  # GUI entry point and pywebview startup
├── manage.py               # process/management helpers
├── api/abstract/           # SoftwareManager ABC + shared model/handler/cache contracts
├── view/
│   ├── core/controller.py  # GenericSoftwareManager orchestration
│   ├── webview/            # pywebview front-end + AtlasApi bridge
│   ├── tray.py             # optional AppIndicator/SNI tray integration
│   └── util/               # i18n and helper utilities
├── gems/<type>/            # one backend per package type
├── commons/                # shared system/config/version utilities
└── cli/                    # command-line front-end

docs/
├── STATUS.md               # live handoff baton
├── BACKLOG.md              # longer-horizon feature/QoL menu
├── ARCHITECTURE.md         # this file
├── ROADMAP.md              # historical Rust roadmap/verdict
├── DEVELOPMENT.md          # build / run / test
└── plans/                  # feature design / implementation notes
```

---

## 7. Development conventions

- Python follows PEP 8.
- Plan non-trivial backend/engine changes in `docs/plans/YYYY-MM-DD-<feature>.md` before
  implementation.
- Use strangler-fig changes for risky behavior: add the new path, keep the old fallback,
  verify, then remove the old path separately.
- Measure before adding caches, thread pools, native code, or other complexity.
- Keep Arch official repo packages and AUR packages visibly distinct in UI and data model.
- Do not reintroduce Qt, Rust, Snap/Debian/Web defaults, or native browser dialogs without
  explicit sign-off.
- Update `docs/STATUS.md` before handing off any session that changes code or project
  direction.
