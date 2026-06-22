# Atlas Development Guide

How to build, run, and test Atlas. For contribution etiquette (bug reports, translations,
PR expectations) see the top-level [CONTRIBUTING.md](../CONTRIBUTING.md).

> Atlas is **pure Python** — there is no native/Rust extension to build. (A Rust experiment
> existed briefly and was removed; see the verdict in [ROADMAP.md](./ROADMAP.md).)

---

## 1. Prerequisites

| Tool | Why |
|------|-----|
| Python ≥ 3.9 | Application runtime |
| GTK 3 + WebKitGTK + PyGObject | The pywebview GUI window |
| `pacman` (Arch) | Required to exercise the Arch gem locally |

On Arch: `sudo pacman -S --needed python python-pip gtk3 webkit2gtk python-gobject git`
(use `webkit2gtk-4.1` if that's what your distro ships). Python runtime deps live in
`requirements.txt`.

---

## 2. Setup, build & run

```bash
# from the repo root
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e .            # plain setuptools — no Rust/cargo

# run
atlas              # GUI (pywebview window)            → atlas.app:main
atlas --logs       # GUI with verbose logging / webview devtools
atlas-cli          # command-line interface
# or, without entry points:
python -m atlas.app --logs
```

Runtime files (see ARCHITECTURE §5): config in `~/.config/atlaspm`, cache in
`~/.cache/atlaspm`, logs/temp in `/tmp/atlaspm@$USER`.

---

## 3. Testing

```bash
python -m pytest                      # or: python -m unittest discover -s tests
```

Tests must not depend on a real system — mock `run_cmd` / HTTP / inputs and assert on the
parsed result, not live `pacman`/network. The webview API (`atlas/view/webview/api.py`)
and watcher are covered under `tests/view/webview/`.

> **GUI behaviour can't be unit-tested headless.** The pywebview window, the
> blocking-modal dialogs (root password, confirmations), and notifications need a real
> run to verify — launch `atlas --logs` and check by hand.

---

## 4. Notes for engine work

- **WebKitGTK has no native JS dialogs** (`window.prompt/confirm/alert` no-op). All dialogs
  are HTML modals: the Python worker thread calls `evaluate_js("showXModal(...)")` and
  blocks on a `threading.Event`; a `js_api` callback (`submit_*`) releases it. Never
  reintroduce a `window.*` dialog.
- **Plan non-trivial backend changes** in `docs/plans/YYYY-MM-DD-<feature>.md` first.
- **Don't add native code / extra dependencies without a measured reason.** Atlas is
  I/O-bound (pacman/AUR/network/makepkg); CPU rewrites rarely move the needle here — that's
  why the Rust extension was dropped.

---

## 5. Code style

- **Python:** [PEP 8](https://www.python.org/dev/peps/pep-0008/).
- **Commits:** conventional prefixes (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`,
  `test:`); one logical change per commit.

---

## 6. Common pitfalls

| Symptom | Likely cause |
|---------|-------------|
| Suggestions/categories don't update | Cached under `~/.cache/atlaspm/<gem>/`; delete the cached file or wait for expiry. Data comes from [atlas-files](https://github.com/Vatteck/atlas-files) `main`. |
| A modal/dialog never returns | A `js_api` `submit_*` callback isn't firing — check the modal's button handler in `main.js`. |
| Tests need a real system | Mock `run_cmd` / inputs; assert via parsed output, not live `pacman`/network. |

---

## 7. Packaging — publishing to the AUR

The AUR package **`atlas-pm-git`** lives in its own git repo
(`ssh://aur@aur.archlinux.org/atlas-pm-git.git`) with `PKGBUILD` + `.SRCINFO` at the root —
it can't reference this repo's `linux_dist/arch/` subfolder. So `linux_dist/arch/PKGBUILD` is
the **source of truth**, and the AUR copy is synced from it.

**Both AUR packages are now published automatically by CI** on push to `master`
(`.github/workflows/aur-publish.yml` for `atlas-pm-git`, `aur-publish-stable.yml` for the stable
`atlas-pm`) — you normally don't run the publish scripts by hand. The manual path below remains for
local pushes / first-time registration / debugging.

Edit `linux_dist/arch/PKGBUILD`, then publish in one step:

```bash
./linux_dist/arch/publish-aur.sh ["commit message"]   # add --dry-run to preview
```

It clones/resets the AUR repo (default `~/Projects/atlas-aur`, override with `$ATLAS_AUR_DIR`),
copies the PKGBUILD, **regenerates `.SRCINFO`** (so the two can't drift), mirrors `.SRCINFO`
back here, and commits + pushes only if something changed. Needs your AUR SSH key loaded.

> The icon/code fixes themselves need **no** PKGBUILD change — `atlas-pm-git` builds from
> `master` HEAD, so a user `paru -S atlas-pm-git` rebuild picks them up. Only edit/publish the
> PKGBUILD when **packaging metadata** changes (deps, install paths, the desktop entry).

### 7.1 Stable releases — `atlas-pm`

The stable **`atlas-pm`** package is now **registered + live on the AUR** (first published at 0.14.0).
Cut a new stable release when you have a commit you'd hand a stranger as "a release" (real users
wanting stability, not HEAD). Its recipe lives at `linux_dist/arch/release/PKGBUILD` (built from
a tagged tarball with a **pinned** sha256, not `master`); CI then auto-publishes it.

```bash
./linux_dist/arch/release.sh            # version from atlas/__init__.py (or pass 0.13.0)
./linux_dist/arch/release.sh --publish  # also sync + push the atlas-pm AUR repo
```

It runs the test suite, tags `vX.Y.Z` + pushes the tag (GitHub only generates the tarball once
the tag exists), pins the tarball's sha256 into `release/PKGBUILD`, regenerates `release/.SRCINFO`,
and prints the commit + AUR-publish commands. Without `--publish` it touches nothing on the AUR.
Bump `atlas/__init__.py`'s `__version__` (and tidy `CHANGELOG.md`) before releasing. For a
packaging-only re-release of the same version, bump `pkgrel` by hand — the script leaves it alone
unless the version changed.

Before tagging, walk **[RELEASE_SMOKE.md](RELEASE_SMOKE.md)** — a short manual pass for the
environment-dependent behaviour CI can't cover (KDE vs GNOME, tray, terminals, missing tools).
`atlas --self-check` prints the runtime environment (desktop, display server, detected tools) to
make that pass deterministic. CI itself now includes an **Arch — tests + package build** job that
runs the suite on real Arch and verifies the wheel build + install layout.
