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

1. **Phase 0 — harden & instrument the boundary** *(do this before adding more Rust)*
   - Replace the silent `except Exception: pass` in `atlas/gems/arch/dependencies.py`
     with logging gated on `ATLAS_RS_DEBUG`.
   - Add an `ATLAS_DISABLE_RS=1` switch to force the Python path for A/B + triage.
   - Stand up a benchmark harness (start from `rust/test_rs.py`) to quote real speedups.
   - Expand `resolver.rs` / `pacman.rs` unit tests with mocked `SysInterface`.
2. **Phase 1 — native Arch update detection** (`updates.py`), pulling in a native
   version-compare + dependency-expression primitive first.

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

---

## Known gaps / gotchas (don't get burned)

- **Silent fallback hides Rust bugs.** `dependencies.py:~419` swallows all exceptions, so
  a broken native path degrades to "slow but works" with no signal. Fix in Phase 0.
- **`needs_providers` not wired to Python.** `resolver.rs` produces
  `choices`/`providers_repos`, but `lib.rs:map_missing_deps` only serializes
  `status`/`dependencies`/`deps_data`. The native path therefore only handles
  `status == "success"`; everything else must fall back. See atlas_rs-API.md.
- **`deps_data` crosses as JSON strings**, not nested dicts (caller must `json.loads`).
  Known wart; candidate for native `PyDict` conversion later.
- **Rebuild reminder:** editing `rust/src/*` requires `pip install -e .` to take effect.
- Large Python files to read in sections, not whole: `controller.py` (~192 KB),
  `updates.py` (~42 KB), `pacman.py` (~38 KB).

---

## Decision log (append-only; newest first)

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
