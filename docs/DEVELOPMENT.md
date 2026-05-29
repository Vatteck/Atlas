# Atlas Development Guide

How to build, run, and test Atlas — including the `atlas_rs` Rust extension — and the
conventions for contributing engine work. For contribution etiquette (bug reports,
translations, PR expectations) see the top-level [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## 1. Prerequisites

| Tool | Why |
|------|-----|
| Python ≥ 3.8 (3.6+ nominally) | Application runtime |
| Rust toolchain (`rustc`, `cargo`) via [rustup](https://rustup.rs) | Builds `atlas_rs` |
| `setuptools-rust` | Bridges Cargo into the Python build |
| pywebview + a system webview (GTK/Qt WebKit) | GUI window |
| `pacman` (Arch) | Required to exercise the Arch gem locally |

Python runtime deps live in `requirements.txt`; build deps in `pyproject.toml`
(`[build-system].requires`).

---

## 2. First-time setup

```bash
# from the repo root
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install setuptools-rust
```

---

## 3. Building the Rust extension

The crate lives in `rust/` (`atlas_rs`, `crate-type = ["cdylib"]`). `setup.py`
declares it as a `RustExtension` installed at **`atlas.gems.arch.atlas_rs`** (see the
`rust_extensions=[...]` line). There are two ways to build it.

### 3a. Develop loop (recommended)
Build the extension in place so Python picks it up from the source tree:

```bash
pip install -e .            # builds the .so and installs Atlas in editable mode
```

Re-run after any change to `rust/src/*`. The compiled artifact lands at
`atlas/gems/arch/atlas_rs.cpython-<ver>-<arch>-linux-gnu.so`.

> **Build profile matters.** `setup.py` pins `debug=False`, so installs build *release*
> (optimized) Rust. This is deliberate: a debug `atlas_rs` was measured ~4× slower than
> the Python it replaced, while release is ~2× faster. If you build by hand for
> benchmarking, use `cargo build --release`. If `pip install -e .` fails with a
> `rust/target/.../incremental ... does not exist` error, prefix it with
> `CARGO_INCREMENTAL=0`.

### 3b. Iterating on Rust alone
For fast compile feedback without reinstalling the Python package:

```bash
cargo check --manifest-path rust/Cargo.toml     # type-check, fastest
cargo build --manifest-path rust/Cargo.toml     # full build
cargo test  --manifest-path rust/Cargo.toml     # run Rust unit tests
cargo fmt   --manifest-path rust/Cargo.toml     # format before committing
```

Once it checks out, run `pip install -e .` (or copy the artifact) so the Python side
sees the new code.

> If the `.so` is missing or fails to import, Atlas still runs — every Rust-backed
> function falls back to its Python implementation (see ARCHITECTURE §3.2). A working
> build is required to exercise the native path.

---

## 4. Running Atlas

```bash
atlas              # GUI (pywebview window)         → atlas.app:main
atlas --logs       # GUI with verbose logging / webview debug
atlas-tray         # start attached to the system tray
atlas-cli          # command-line interface
```

Or without installed entry points:

```bash
python -m atlas.app --logs
```

Runtime files (see ARCHITECTURE §5): config in `~/.config/atlaspm`, cache in
`~/.cache/atlaspm`, logs/temp in `/tmp/atlaspm@$USER`.

---

## 5. Testing

### Python
```bash
python -m pytest                      # or:
python -m unittest discover -s tests
```

### Rust
```bash
cargo test --manifest-path rust/Cargo.toml
```
Rust logic is written against the `SysInterface` trait (`rust/src/sys.rs`) so tests use
a **mocked** implementation — no live `pacman` or network required.

### Comparing native vs Python paths
```bash
ATLAS_DISABLE_RS=1 atlas-cli ...      # force the pure-Python path (A/B + triage)
ATLAS_RS_DEBUG=1   atlas-cli ...      # surface native-path errors instead of silent fallback
```
These switches are implemented in `atlas/gems/arch/native.py` and honoured by every
native call site. Default behaviour (no env set) is unchanged: try native, fall back
silently on any problem.

---

## 6. Engine contribution workflow

Backend / Rust-migration work follows a fixed loop so each step is reviewable and the
app stays shippable throughout:

1. **Design doc** — `docs/plans/YYYY-MM-DD-<feature>-design.md`: state the Python↔Rust
   boundary and the exact payload schema.
2. **Implementation plan** — `docs/plans/YYYY-MM-DD-<feature>-implementation.md`:
   task-by-task, with the verify/commit steps for each task.
3. **Baseline** — capture a Python benchmark for the workload you're speeding up.
4. **Implement in Rust** against `SysInterface`; no direct I/O in logic code.
5. **Unit-test** with a mocked `SysInterface`.
6. **Expose** via PyO3 in `rust/src/lib.rs` and register in the `#[pymodule]`.
7. **Wire in** on the Python side **behind the existing fallback** — do not delete the
   Python implementation in the same change.
8. **Verify** identical results native vs Python on a real system; record the speedup.

See the full checklist in [ROADMAP.md](./ROADMAP.md#per-migration-checklist).

---

## 7. Code style

- **Python:** [PEP 8](https://www.python.org/dev/peps/pep-0008/).
- **Rust:** `cargo fmt`; keep I/O behind `SysInterface`; prefer single-pass / zero-copy
  parsing for hot paths.
- **Commits:** conventional prefixes already in use (`feat:`, `fix:`, `refactor:`,
  `docs:`, `chore:`, `test:`). Keep one logical change per commit.

---

## 8. Common pitfalls

| Symptom | Likely cause |
|---------|-------------|
| Rust changes have no effect at runtime | Forgot to rebuild — re-run `pip install -e .`. |
| `ImportError: atlas_rs` but app still works | `.so` not built/installed; you're silently on the Python fallback. |
| Native path "works but slow" | A Rust exception is being swallowed by the fallback — run with `ATLAS_RS_DEBUG=1`. |
| `.so` for wrong Python version | Rebuild against your active interpreter (the filename encodes the ABI). |
| Tests need a real system | Use the mocked `SysInterface`; don't call live `pacman`/network in unit tests. |
