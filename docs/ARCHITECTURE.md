# Atlas Architecture

> **Note (2026-06-01): Atlas is pure Python.** The Rust `atlas_rs` extension and the
> Python↔Rust boundary described later in this doc were **removed** — a package manager is
> I/O-bound, so the native path wasn't worth its toolchain. Treat any Rust / `atlas_rs` /
> `SysInterface` references below as historical. The UI is **pywebview**, and Atlas is
> **Arch-focused** (Arch/AUR/Flatpak/AppImage on by default; Snap/Debian/Web off).

Atlas (a fork of **bauh**) is an Arch-focused graphical package manager for Linux. It
manages Arch/AUR, Flatpak, and AppImage (plus optional Snap, Debian, and native Web apps)
behind a single interface.

Atlas is mid-transition along two axes at once:

1. **UI:** legacy Qt5 → a modern **pywebview** front-end (HTML/CSS/JS).
2. **Engine:** pure-Python backends → a hybrid where hot paths are rewritten in
   **Rust** and exposed to Python through **PyO3** (the `atlas_rs` native module).

This document is the map. It describes the layers, how they talk to each other, and
the conventions that keep the Python↔Rust boundary sane. For *what to migrate next*
see [ROADMAP.md](./ROADMAP.md); for *how to build and run* see
[DEVELOPMENT.md](./DEVELOPMENT.md); for the native module surface see
[atlas_rs-API.md](./atlas_rs-API.md).

---

## 1. Bird's-eye view

```
                        ┌──────────────────────────────────────────┐
                        │              pywebview window              │
                        │   index.html · main.js · style.css        │  ← Front-end
                        └───────────────────┬──────────────────────┘
                                            │  JS ↔ Python bridge (pywebview)
                        ┌───────────────────▼──────────────────────┐
                        │        atlas/view/webview/api.py          │
                        │              (AtlasApi)                    │  ← View / API layer
                        └───────────────────┬──────────────────────┘
                                            │  Python calls
                        ┌───────────────────▼──────────────────────┐
                        │   atlas/view/core/controller.py           │
                        │      GenericSoftwareManager               │  ← Orchestration
                        │  (dispatches to enabled gems, lazily)     │
                        └───────────────────┬──────────────────────┘
            ┌───────────────┬───────────────┼───────────────┬───────────────┐
            ▼               ▼               ▼               ▼               ▼
       ┌─────────┐    ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
       │  arch   │    │ flatpak │     │  snap   │     │appimage │     │  web /  │  ← Gems
       │  gem    │    │  gem    │     │  gem    │     │  gem    │     │ debian  │   (backends)
       └────┬────┘    └─────────┘     └─────────┘     └─────────┘     └─────────┘
            │  hot paths
            ▼
    ┌───────────────────┐
    │     atlas_rs      │   native Rust extension (PyO3), built into
    │  (Rust / PyO3)    │   atlas/gems/arch/atlas_rs.*.so
    └───────────────────┘
```

Each gem implements the **`SoftwareManager`** abstract base class
(`atlas/api/abstract/controller.py:154`). The `GenericSoftwareManager`
(`atlas/view/core/controller.py`) holds the set of gems and fans operations out to
the ones that are enabled, ideally **lazily** (only initializing a backend when its
view is actually requested — see the engine design doc and ROADMAP "lazy init").

---

## 2. Layers

### 2.1 Front-end — `atlas/view/webview/`
- `index.html`, `main.js`, `style.css` — the rendered UI.
- Runs inside a native window via **pywebview** (`webview.create_window` /
  `webview.start` in `atlas/app.py`).
- Calls into Python through the pywebview JS↔Python bridge; the bound object is
  `AtlasApi`.
- Supporting modules: `activity_log.py`, `watcher.py` (progress/process watching),
  `export.py`.

> The legacy Qt5 UI (`view/qt/`, QSS styles) has been purged as part of the rebrand.
> Anything referencing Qt forms/widgets is dead and should not be reintroduced.

### 2.2 View / API layer — `atlas/view/webview/api.py` (`AtlasApi`)
- The single surface the front-end is allowed to call.
- Translates UI intents (search, install, upgrade, downgrade, uninstall, launch) into
  calls on the `GenericSoftwareManager`.
- Responsible for threading concurrent requests so the UI never blocks (target:
  a shared `ThreadPoolExecutor` — see ROADMAP).

### 2.3 Orchestration — `atlas/view/core/controller.py` (`GenericSoftwareManager`)
- Owns the list of gem managers and the app config (`~/.config/atlaspm/config.yml`).
- Routes each operation to the gem(s) that own the relevant package type.
- Drives `prepare()` on gems. The performance goal is **lazy** preparation: only
  enabled gems, only when needed, instead of eagerly booting every backend at launch.

### 2.4 Gems (backends) — `atlas/gems/<type>/`
Each subdirectory is a self-contained backend implementing `SoftwareManager`. The
Arch gem is the largest and the current focus of the Rust migration:

| File | Role | Size¹ |
|------|------|------|
| `controller.py` | Arch `SoftwareManager` implementation | ~192 KB |
| `updates.py` | Update detection / planning | ~42 KB |
| `pacman.py` | pacman CLI wrapper + output parsing | ~38 KB |
| `dependencies.py` | Dependency graph resolution (pure Python; I/O+UI-bound) | ~31 KB |
| `worker.py` | Background index/sync workers | ~25 KB |
| `aur.py` | AUR RPC client | ~8.5 KB |
| `sorting.py`, `mapper.py`, `download.py`, ... | Supporting logic | — |

¹ Sizes are a rough indicator of complexity / migration effort, not a contract.

### 2.5 Native engine — `atlas_rs` (Rust, in `rust/`)
- Cargo crate `atlas_rs`, `crate-type = ["cdylib"]`, built via **setuptools-rust** as a
  PyO3 extension module and installed at `atlas.gems.arch.atlas_rs` (see `setup.py`).
  `setup.py` pins `debug=False` so installs are optimized (release).
- `lib.rs` is the only module. It exposes a single function: **`map_srcinfo`**
  (`.SRCINFO`/pacman field parser, ~2× vs Python — a small, CPU-bound result).
- Deliberately minimal: a native dependency resolver and a native `pacman -Si` parser
  were prototyped and **removed** after measurement (I/O-bound and marshalling-bound
  respectively). See [atlas_rs-API.md](./atlas_rs-API.md) and the engine lesson below.
- Crate deps: just `pyo3` (the `serde`/`ureq`/`regex` deps went with the removed code).

---

## 3. The Python ↔ Rust boundary

This is the most important contract in the codebase, so it gets its own section.

### 3.1 Design principle: coarse-grained calls
Cross-language calls are not free. Hand Rust an **entire task** and get a finished
result back; never have Rust call into Python in a tight loop. `map_srcinfo` is the
template: Python passes one `.SRCINFO` string, Rust parses it in a single pass and
returns the parsed dict.

### 3.2 The fallback pattern (strangler fig)
Every native function is reached through `atlas/gems/arch/native.py` and keeps a
pure-Python fallback. `native.load()` returns the module or `None` (when the build is
missing or `ATLAS_DISABLE_RS` is set); the caller tries native, then falls back. Example
from `atlas/gems/arch/srcinfo.py`:

```python
def map_srcinfo(string, pkgname=None, fields=None):
    atlas_rs = native.load(logger)          # None if disabled/unavailable
    if atlas_rs is not None:
        try:
            return atlas_rs.map_srcinfo(string, pkgname, fields)
        except Exception:
            native.report_failure(logger, 'map_srcinfo')   # logged under ATLAS_RS_DEBUG
    return _map_srcinfo_py(string, pkgname, fields)         # pure-Python fallback
```

This keeps Atlas working even if the extension failed to build. **Rules:** never delete a
fallback in the same change that adds the native path; import the module by its qualified
name (a bare `import atlas_rs` does **not** resolve at runtime); and surface native
failures with `ATLAS_RS_DEBUG=1` rather than swallowing them silently.

### 3.3 What belongs in Rust — the hard-won rule
Only port operations that are **CPU-bound and return a small result.** Two prototypes
were removed after measurement proved otherwise:
- a native **dependency resolver** — the work is live pacman/AUR I/O + recursion +
  watcher-driven (UI) provider choices, not CPU; a faithful port needs Rust→Python
  callbacks and gains nothing.
- a native **`pacman -Si` parser** — only ~1.2× because it returns ~100 per-package
  dicts, so PyO3 result-marshalling dominates the parse win.

`map_srcinfo` survives because its result is one compact dict. Before adding a native
path, ask: is it CPU-bound, and is the result small? If not, keep it in Python. See
[ROADMAP.md](./ROADMAP.md) and [STATUS.md](./STATUS.md) for the measurements.

---

## 4. Application entry points

Defined in `pyproject.toml` / `setup.py`:

| Command | Target | Purpose |
|---------|--------|---------|
| `atlas` | `atlas.app:main` | Launch the GUI (pywebview window) |
| `atlas-tray` | `atlas.app:tray` | Launch attached to the system tray |
| `atlas-cli` | `atlas.cli.app:main` | Command-line interface |

`atlas/app.py:main` builds the gem managers, wraps them in a `GenericSoftwareManager`,
binds an `AtlasApi`, and opens the pywebview window pointed at
`view/webview/index.html`.

---

## 5. On-disk layout (runtime)

| Path | Contents |
|------|----------|
| `~/.config/atlaspm` (`/etc/atlaspm` as root) | Configuration (`config.yml`, gem configs) |
| `~/.cache/atlaspm` (`/var/cache/atlaspm` as root) | Installed-app data, AUR index, databases |
| `/tmp/atlaspm@$USER` | Logs and temporary files |

---

## 6. Source tree quick reference

```
atlas/
├── app.py                  # entry points (main, tray)
├── manage.py               # process/management helpers
├── api/abstract/           # SoftwareManager ABC + shared model/handler/cache contracts
├── view/
│   ├── core/controller.py  # GenericSoftwareManager (orchestrator)
│   ├── webview/            # pywebview front-end + AtlasApi bridge
│   └── util/               # i18n, helpers
├── gems/<type>/            # one backend per package type
├── commons/                # shared system utilities (version_util, etc.)
└── cli/                    # command-line front-end

rust/
├── Cargo.toml              # atlas_rs crate
└── src/                    # lib.rs (map_srcinfo only)

docs/
├── ARCHITECTURE.md         # this file
├── ROADMAP.md              # Rust migration plan
├── DEVELOPMENT.md          # build / run / test
├── atlas_rs-API.md         # native module reference
└── plans/                  # per-feature design + implementation docs
```

---

## 7. Conventions in one paragraph

New backend work follows a documented loop: write a **design doc** and an
**implementation plan** under `docs/plans/` (`YYYY-MM-DD-<feature>-{design,implementation}.md`),
build the Rust path behind a Python fallback, expose it through PyO3 in `lib.rs`, wire
it into the owning gem, and verify against both real and mocked system interfaces.
Python follows PEP 8; Rust follows `cargo fmt`. Keep the boundary coarse, keep the
fallback until the native path is proven.
