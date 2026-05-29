# STATUS — the handoff baton

> **This is the single most important file for cross-agent continuity.** It is the live
> state of the project. Read it at the start of every session; update it at the end of
> every session that changes code (see AGENTS.md §8). Keep it short and current — when an
> item is stale, fix it or delete it.

**Last updated:** 2026-05-29
**Version:** 0.10.7
**Working branch:** `master` (use short-lived branches for larger features; run `git branch` to see what's active)

---

## Current focus

Migrating the **Arch Linux engine hot paths to Rust** (`atlas_rs` via PyO3), hot paths
first, behind Python fallbacks. Phase 0 (instrument/measure) done; now wiring proven
parsers in (Phase 2 category).

## Next (per ROADMAP, hot paths first)

**Both planned tracks are essentially complete.** The Rust migration reached its sensible
end (only `map_srcinfo` earns its keep). And the Python-side startup wins (option 2) turn
out to be **already implemented + unit-tested** (verified 2026-05-29):
- `GenericSoftwareManager.prepare()` is lazy (only the config step is eager);
  per-manager lazy prep via `_ensure_prepared`/`_can_work` (per-manager locks).
- `AtlasApi` runs prepare off the UI thread via a shared `ThreadPoolExecutor(max_workers=5)`.
- Covered by `tests/view/webview/test_lazy_load.py`.

Remaining, optional & low-value: route the controller's ad-hoc `Thread(...)` spawns
(search / read-installed / suggestions) through a shared pool. Marginal benefit, real
risk — only do it with a measured reason. **Recommended instead:** manually launch
`atlas` to confirm real startup behavior and capture a launch-time baseline (no automated
GUI test exists).

The Rust migration verdict (after measuring everything): the PyO3 boundary only pays off
for **CPU-bound ops with small results**. `map_srcinfo` qualifies (~2×). The dependency
resolver (I/O+UI-bound) and the pacman info parser (marshalling-bound) did not and were
removed. Don't re-attempt them without reading the decision log.

See [ROADMAP.md](ROADMAP.md) for the full phased plan.

---

## Done

- Rebrand bauh → Atlas (namespaces, config paths `~/.config/atlaspm` etc., UI strings).
- Qt5 UI purged; pywebview front-end (`atlas/view/webview/`) in place.
- `atlas_rs` build pipeline (PyO3 + setuptools-rust, `debug=False`), installed at
  `atlas.gems.arch.atlas_rs`. Crate is now `lib.rs` only; deps trimmed to just `pyo3`
  (`.so` ~621 KB, down from 3.6 MB).
- `map_srcinfo` — native `.SRCINFO`/pacman field parser (~2×), with a Python fallback
  in `srcinfo.py`. **The only surviving native function.**
- **Native dependency resolver removed** (`resolver.rs`/`aur.rs`/`pacman.rs`/`sys.rs` +
  `map_missing_deps`): I/O+UI-bound, not a useful Rust target (2026-05-29).
- Documentation set: ARCHITECTURE, ROADMAP, DEVELOPMENT, atlas_rs-API; cross-agent
  onboarding (AGENTS.md / CLAUDE.md / GEMINI.md) + this baton.
- **Phase 0 complete:** boundary instrumentation (`native.py` switches), `deps_data`
  schema fix, benchmark harness (`benchmarks/bench_srcinfo.py`), and the release-build
  fix (`setup.py debug=False`).
- **Native import fix (critical):** `native.load()` imported bare `atlas_rs`, which never
  resolves at runtime → the native path was dormant in production. Now imports
  `from atlas.gems.arch import atlas_rs`.
- **Native pacman info parser: tried then reverted.** Wired into `map_updates_data` and
  parity-tested, but only ~1.2× (marshalling-bound), so reverted to cut maintenance.
  Kept the clean `_parse_info_output_py` extraction (+ its correctness test). Lesson
  recorded in `benchmarks/README.md` and the roadmap.
- **map_srcinfo fallback restored** (`atlas/gems/arch/srcinfo.py`): native-first via
  `native.load()` with the original pure-Python parser as fallback; `aur.py` now imports
  from there. Closes the last native path with no fallback. Parity-tested (incl. `fields`).
- **Native resolver retired** (2026-05-29): removed the 4 dead Rust modules +
  `map_missing_deps` and trimmed Cargo deps. `map_srcinfo` still passes; full suite green.
- Full Python suite 183 — all green. (cargo test: 0 — `map_srcinfo` is covered by the
  Python parity test `test_srcinfo.py`.)

---

## Known gaps / gotchas (don't get burned)

- **Tray mode is gone (was broken).** The rebrand purged Qt but left `tray.py`/`manage.py`
  importing the deleted `atlas.view.qt.*` — `atlas-tray` crashed on launch. Removed them +
  the `atlas-tray` entry point + `--tray` arg + `context.new_qt_application`/`set_theme`
  (2026-05-29). README roadmap notes a non-Qt tray could be reintroduced.
- **Residual PyQt5 coupling remains** (not yet cleaned): `view/core/settings.py`
  (`qt_style` property), `view/util/util.py` (`QCoreApplication.exit()`),
  `stylesheet.py`, and `app.py`'s optional HDPI block, plus `pyqt5` in pyproject deps.
  The webview GUI still pulls in PyQt5 through these. Decide later whether to fully
  de-Qt or keep PyQt5 as an optional dep. Verify each is actually reachable before
  removing.
- **App run-status:** `atlas` (GUI) and `atlas-cli` import and `atlas-cli --help` runs.
  The pywebview GUI has **not** been launched end-to-end in this environment (needs a
  display). Manual `atlas` launch still recommended.

- ~~**Silent fallback hides Rust bugs.**~~ Addressed: native calls now go through
  `atlas/gems/arch/native.py`; run with `ATLAS_RS_DEBUG=1` to log native failures, or
  `ATLAS_DISABLE_RS=1` to force the Python path. (Default behaviour still falls back
  silently.)
- ~~**`map_srcinfo` had no Python fallback.**~~ Fixed: `atlas/gems/arch/srcinfo.py`
  wraps native with the original Python parser; a missing `.so` no longer breaks the
  Arch gem at import. (Native and Python verified to agree, including `fields` cases.)
- **Don't re-attempt a native dependency resolver.** Removed 2026-05-29. The Python
  `map_missing_deps` is I/O-bound (pacman/AUR), recursive, and UI-coupled (watcher
  provider choices) — not CPU. A native port needs Rust→Python callbacks and isn't
  faster. The prototype also re-derived everything, ignoring caller context.
- **Lesson — only port CPU-bound ops with small results.** The native pacman info parser
  measured only ~1.2× (PyO3 result-marshalling + list→set conversion dominate when
  returning many dicts) and was reverted; the resolver was I/O-bound. `map_srcinfo`
  (~2×, one compact dict) is the shape that works. Weigh CPU-vs-I/O and result size
  before any new native path.
- **Rebuild reminder:** editing `rust/src/*` requires `pip install -e .` to take effect.
  If that fails with a `rust/target/debug/incremental/... does not exist` error, build
  with `CARGO_INCREMENTAL=0` (Cargo's incremental dirs churn during setuptools' walk).
- ~~**Debug builds are slower than Python.**~~ Fixed via `setup.py debug=False` (installs
  are now release). The benchmark proved a debug `atlas_rs` runs ~4× *slower* than the
  Python it replaced; release runs ~2× faster. **Always benchmark a release build.**
- Large Python files to read in sections, not whole: `controller.py` (~192 KB),
  `updates.py` (~42 KB), `pacman.py` (~38 KB).

---

## Decision log (append-only; newest first)

- **2026-05-29** — Ran the app for the first time; found `atlas-tray` broken (dead Qt
  imports the rebrand purge missed). Removed the broken tray + orphaned `manage.py` +
  `new_qt_application`/`set_theme` + the `atlas-tray` entry point and `--tray` arg.
  `context.py` no longer needs PyQt5. README/STATUS updated; tray reintro is roadmapped.
- **2026-05-29** — Retired the native dependency resolver: removed `resolver.rs`,
  `aur.rs`, `pacman.rs`, `sys.rs`, the `map_missing_deps` PyO3 fn, and the `serde`/
  `serde_json`/`ureq`/`regex` deps. Reason: I/O+UI-bound, not a viable Rust target (a
  faithful drop-in needs Rust→Python callbacks for pacman/AUR/watcher and wouldn't be
  faster). `lib.rs` is now `map_srcinfo` only; `.so` 3.6 MB → 621 KB. Migration verdict:
  port only CPU-bound ops with small results. Pivoting to Python-side startup wins.
- **2026-05-29** — Reverted the native pacman info parser (~1.2×, marshalling-bound) to
  cut maintenance surface; kept the `_parse_info_output_py` extraction + test. Confirms
  the rule: only port parsers with small results.
- **2026-05-29** — Restored a Python fallback for `map_srcinfo` (`srcinfo.py`); it was the
  only native function with none, so a missing `.so` would have broken the Arch gem.
  Native↔Python parity verified (incl. `fields`).
- **2026-05-29** — Wired native pacman `-Si` parser into `map_updates_data` (parity-tested,
  ~1.2×). Fixed the critical dormant-native import bug (bare `import atlas_rs` never
  resolved). Disabled the non-faithful native `map_missing_deps`. Chose the pacman-parser
  task after finding version-compare is NOT the update hot path (pacman -Qu does repo
  comparison; per-call vercmp across PyO3 would be slower than Python).
- **2026-05-28** — Phase 0 closed with a benchmark (`benchmarks/bench_srcinfo.py`). It
  revealed `pip install -e .` shipped a *debug* `atlas_rs` (~4× slower than Python);
  pinned `setup.py debug=False` → release builds, native now ~2× faster. Lesson encoded:
  always measure release builds.
- **2026-05-28** — Fixed native `deps_data` schema: Rust emits canonical short keys via
  per-source `to_deps_data()`; pacman.rs parses Description/Download/Installed sizes.
  Rust tests 4→13; verified end-to-end on a real package. Plans under `docs/plans/`.
- **2026-05-28** — Phase 0 instrumentation: all native (`atlas_rs`) calls route through
  `atlas/gems/arch/native.py` with `ATLAS_RS_DEBUG` / `ATLAS_DISABLE_RS` switches.
  Default still falls back silently; switches add visibility + an escape hatch.
- **2026-05-28** — Adopted AGENTS.md as the single canonical agent manual; CLAUDE.md and
  GEMINI.md are thin redirects to avoid drift across Claude/Codex/Gemini.
- **2026-05-28** — Migration strategy fixed as **strangler-fig, hot paths first**: Rust
  added behind Python fallbacks, fallback removed only after the native path is proven.
- **2026-05-28** — Python↔Rust boundary is **coarse-grained**: one whole task per call,
  no Rust→Python callbacks (rationale in ARCHITECTURE §3).

---

## Template for a STATUS update (copy when editing)

```
**Last updated:** YYYY-MM-DD
- Moved <item> from Next → Done.
- New Current focus: <…>. New Next: <…>.
- New gotcha discovered: <…> (and where it lives).
- Decision: <what + why>.
```
