# Atlas Architecture

Atlas (formerly **bauh**) is an All-In-One graphical package manager for Linux. It
manages AppImage, Arch/AUR, Debian, Flatpak, Snap, and native Web applications behind
a single interface.

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
| `dependencies.py` | Dependency graph resolution (now Rust-backed) | ~31 KB |
| `worker.py` | Background index/sync workers | ~25 KB |
| `aur.py` | AUR RPC client | ~8.5 KB |
| `sorting.py`, `mapper.py`, `download.py`, ... | Supporting logic | — |

¹ Sizes are a rough indicator of complexity / migration effort, not a contract.

### 2.5 Native engine — `atlas_rs` (Rust, in `rust/`)
- Cargo crate `atlas_rs`, `crate-type = ["cdylib"]`, built via **setuptools-rust** as a
  PyO3 extension module and installed at `atlas.gems.arch.atlas_rs` (see `setup.py`).
- Current modules:
  - `lib.rs` — PyO3 entry point; exposes `map_srcinfo` and `map_missing_deps`.
  - `sys.rs` — `SysInterface` trait (`run_command`, `http_get`) + `LiveSys` impl;
    mockable for tests.
  - `pacman.rs` — native pacman info parser (`-Si` / `-Qi` multiline parsing).
  - `aur.rs` — synchronous AUR RPC client (`ureq` + `serde_json`).
  - `resolver.rs` — recursive DFS dependency resolution with cycle detection,
    provider auto-matching, and topological sort.

---

## 3. The Python ↔ Rust boundary

This is the most important contract in the codebase, so it gets its own section.

### 3.1 Design principle: coarse-grained calls
Cross-language calls are not free. The boundary is drawn so Python hands Rust an
**entire task** and gets back a finished result, rather than Rust calling back into
Python in a tight loop. `map_missing_deps` is the template: Python passes the target
package list and flags; Rust shells out to pacman, hits the AUR RPC, builds the graph,
sorts it, and returns the complete resolution in one call.

### 3.2 The fallback pattern (strangler fig)
Every Rust-backed function keeps its pure-Python implementation as a fallback. The
Rust path is tried first; on **any** failure it silently falls through to Python.
Example from `atlas/gems/arch/dependencies.py:404`:

```python
def map_missing_deps(self, ...):
    try:
        import atlas_rs
        import json
        native_res = atlas_rs.map_missing_deps(packages, automatch_providers,
                                               prefer_repository_provider)
        if native_res["status"] == "success":
            for pkg, raw_json in native_res["deps_data"].items():
                deps_data[pkg] = json.loads(raw_json)
            return native_res["dependencies"]
    except Exception:
        pass
    # ... original pure-Python resolution continues here ...
```

This lets Atlas ship and run even where the extension failed to build or a new Rust
path has a regression. **Rule: never delete the Python fallback in the same change
that introduces the Rust path.** Remove fallbacks only once a path is proven, and as
a deliberate, separate step.

> ⚠️ The blanket `except Exception: pass` hides real Rust bugs as "slow but works."
> During development, log the exception (gated behind a debug flag) so regressions in
> the native path are visible. See ROADMAP "harden the boundary."

### 3.3 Data interchange conventions
- Inputs are plain Python types (`List[str]`, `bool`).
- Structured results cross as a `dict` with a `status` discriminator
  (`"success"` / `"needs_providers"`). See [atlas_rs-API.md](./atlas_rs-API.md) for
  the full payload schemas.
- Nested per-package data is currently serialized as **JSON strings** inside the dict
  (`deps_data[pkg] = json.loads(raw_json)`), trading a serialize/parse step for a
  simpler PyO3 conversion. This is a known wart — a candidate for native `PyDict`
  conversion later.

### 3.4 Provider choices stay in Python
When dependency resolution hits an ambiguous virtual package with multiple providers
and auto-matching is off, Rust returns `status: "needs_providers"` with the choices
and their repos, and **Python collects the user's decision** (the UI is Python's job).
The boundary deliberately does not pull UI concerns into Rust.

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
└── src/                    # lib.rs, sys.rs, pacman.rs, aur.rs, resolver.rs

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
