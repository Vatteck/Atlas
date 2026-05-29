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

Open options, in rough priority:
1. **Decide the fate of the native pacman parser.** It's wired + parity-tested but only
   ~1.2× faster (PyO3 result-marshalling dominates when returning many dicts). Either
   accept it (it's correct, behind a fallback) or revert to reduce maintenance. A
   Rust-side PySet builder might push it higher but is likely not worth it.
2. **Rework native `map_missing_deps` into a faithful drop-in** (accept caller context
   instead of re-deriving from live pacman/AUR) — currently disabled, see gaps.
3. **`needs_providers`** correctness path (resolve() only ever returns `success`).
4. **Phase 1 — native Arch update detection** (note: version-compare is NOT the hot path;
   see decision log 2026-05-29).

Before any new native parse port: results that are large structured dicts barely benefit
(~1.2×); small-result ops (like map_srcinfo, ~2×) are the better targets.

See [ROADMAP.md](ROADMAP.md) for the full phased plan.

---

## Done

- Rebrand bauh → Atlas (namespaces, config paths `~/.config/atlaspm` etc., UI strings).
- Qt5 UI purged; pywebview front-end (`atlas/view/webview/`) in place.
- `atlas_rs` build pipeline (PyO3 + setuptools-rust), installed at
  `atlas.gems.arch.atlas_rs`.
- `SysInterface` abstraction (`rust/src/sys.rs`) for mockable shell/HTTP.
- `map_srcinfo` — native `.SRCINFO`/pacman field parser.
- Native pacman `-Si`/`-Qi` info parser (`rust/src/pacman.rs`).
- Synchronous AUR RPC client (`rust/src/aur.rs`).
- Recursive DFS dependency resolver + topological sort + provider matching
  (`rust/src/resolver.rs`), exposed as `map_missing_deps`, wired into
  `dependencies.py` behind a Python fallback.
- Documentation set: ARCHITECTURE, ROADMAP, DEVELOPMENT, atlas_rs-API; cross-agent
  onboarding (AGENTS.md / CLAUDE.md / GEMINI.md) + this baton.
- **Phase 0 complete:** boundary instrumentation (`native.py` switches), `deps_data`
  schema fix, benchmark harness (`benchmarks/bench_srcinfo.py`), and the release-build
  fix (`setup.py debug=False`).
- **Native import fix (critical):** `native.load()` imported bare `atlas_rs`, which never
  resolves at runtime → the native path was dormant in production. Now imports
  `from atlas.gems.arch import atlas_rs`.
- **Native pacman info parser wired** into `pacman.py:map_updates_data` (`-Si` path) +
  `parse_pacman_info` PyO3 fn + parity test. Modest ~1.2× (see gaps/lesson).
- **map_srcinfo fallback restored** (`atlas/gems/arch/srcinfo.py`): native-first via
  `native.load()` with the original pure-Python parser as fallback; `aur.py` now imports
  from there. Closes the last native path with no fallback. Parity-tested (incl. `fields`).
- Rust tests 14, full Python suite 182 — all green.

---

## Known gaps / gotchas (don't get burned)

- ~~**Silent fallback hides Rust bugs.**~~ Addressed: native calls now go through
  `atlas/gems/arch/native.py`; run with `ATLAS_RS_DEBUG=1` to log native failures, or
  `ATLAS_DISABLE_RS=1` to force the Python path. (Default behaviour still falls back
  silently.)
- ~~**`map_srcinfo` had no Python fallback.**~~ Fixed: `atlas/gems/arch/srcinfo.py`
  wraps native with the original Python parser; a missing `.so` no longer breaks the
  Arch gem at import. (Native and Python verified to agree, including `fields` cases.)
- ~~**Native `deps_data` schema mismatch.**~~ Fixed: Rust now emits the canonical
  short-key schema (`d/p/r/v/s/ds/c/des`) via `PacmanPackage::to_deps_data` /
  `AurPackageRaw::to_deps_data`; pacman.rs now parses Description/Download/Installed
  sizes. Verified end-to-end. See `docs/plans/2026-05-28-deps-data-schema-fix-*`.
- **Native `map_missing_deps` disabled (not a faithful drop-in).** It re-derives the
  graph from live pacman/AUR and ignores the caller's pre-fetched inputs (pkgs_data,
  provided_map, remote_*_map, aur_index, deps_data), so wiring it in changed behavior
  and broke mocked tests. `dependencies.py` now always uses Python; the Rust resolver
  stays unit-tested for a future rework that accepts caller context.
- **Native pacman parser is only ~1.2× (lesson).** Returning many structured dicts makes
  PyO3 result-marshalling + the list→set conversion dominate the parse win. Small-result
  parsers (map_srcinfo ~2×) are the better Rust targets. Weigh this before porting more.
- **`needs_providers` not wired to Python.** `resolver.rs` produces
  `choices`/`providers_repos`, but `lib.rs:map_missing_deps` only serializes
  `status`/`dependencies`/`deps_data`, AND `resolve()` never actually returns a
  non-success status (provider auto-matching is unimplemented). (Moot while the native
  resolver is disabled, but relevant when it's reworked.)
- **AUR `d` approximation:** the resolver's AUR path uses the RPC `Depends` field
  directly rather than replicating Python's `extract_required_dependencies`.
- **`deps_data` crosses as JSON strings**, not nested dicts (caller must `json.loads`).
  Known wart; candidate for native `PyDict` conversion later.
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
