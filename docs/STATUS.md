# STATUS — the handoff baton

> **This is the single most important file for cross-agent continuity.** It is the live
> state of the project. Read it at the start of every session; update it at the end of
> every session that changes code (see AGENTS.md §8). Keep it short and current — when an
> item is stale, fix it or delete it.

**Last updated:** 2026-05-28
**Version:** 0.10.7
**Working branch:** `master` (use short-lived branches for larger features; run `git branch` to see what's active)

---

## Current focus

Migrating the **Arch Linux dependency/engine hot paths to Rust** (`atlas_rs` via PyO3),
hot paths first, behind Python fallbacks. The dependency resolver is the first major
piece and is wired in.

## Next (per ROADMAP, hot paths first)

**Phase 0 is complete.** Next is **Phase 1 — native Arch update detection**
(`updates.py`), pulling in a native version-compare + dependency-expression primitive
first. Capture a Python baseline benchmark before starting (release build only!).

Optional correctness follow-up (not perf): implement provider auto-matching + the
`needs_providers` return path so `resolve()` can handle ambiguous virtual packages
(currently it only ever returns `success`).

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
  fix (`setup.py debug=False`). Rust tests 13, Python arch tests 73, all green.

---

## Known gaps / gotchas (don't get burned)

- ~~**Silent fallback hides Rust bugs.**~~ Addressed: native calls now go through
  `atlas/gems/arch/native.py`; run with `ATLAS_RS_DEBUG=1` to log native failures, or
  `ATLAS_DISABLE_RS=1` to force the Python path. (Default behaviour still falls back
  silently.)
- ~~**Native `deps_data` schema mismatch.**~~ Fixed: Rust now emits the canonical
  short-key schema (`d/p/r/v/s/ds/c/des`) via `PacmanPackage::to_deps_data` /
  `AurPackageRaw::to_deps_data`; pacman.rs now parses Description/Download/Installed
  sizes. Verified end-to-end. See `docs/plans/2026-05-28-deps-data-schema-fix-*`.
- **`needs_providers` not wired to Python.** `resolver.rs` produces
  `choices`/`providers_repos`, but `lib.rs:map_missing_deps` only serializes
  `status`/`dependencies`/`deps_data`, AND `resolve()` never actually returns a
  non-success status (provider auto-matching is unimplemented). The native path only
  handles `status == "success"`; everything else falls back. See atlas_rs-API.md.
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
