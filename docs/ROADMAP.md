# Atlas Rust Migration Roadmap (historical)

> **⚠️ CLOSED (2026-06-01): the Rust migration was dropped entirely and `atlas_rs` removed.**
> The verdict from measuring each candidate: a package manager is I/O-bound (pacman / AUR /
> network / makepkg), so native code rarely helps. Only `map_srcinfo` was ever CPU-bound
> with a small result (~2×), and even that parses a file in time dwarfed by the build around
> it — not worth a Rust toolchain + dual implementations. The dependency resolver
> (I/O+UI-bound) and pacman info parser (marshalling-bound) had already been reverted; the
> last surviving path (`map_srcinfo`) is now pure Python again. **This whole document is
> historical** — kept for the rationale. The lesson worth keeping: *only port CPU-bound
> work with a small result, and only with a measured win.* See [STATUS.md](./STATUS.md) for
> what's actually next.

This was the forward plan for moving Atlas's engine from pure Python to a Python+Rust
hybrid. The strategy was **hot paths first**: rewrite the slowest CPU/IO-heavy operations
into `atlas_rs`, keeping the app shippable at every step.

Read [ARCHITECTURE.md](./ARCHITECTURE.md) first — especially §3 (the Python↔Rust
boundary), which this roadmap assumes.

---

## Guiding principles

1. **Strangler fig, not big bang.** Each migration adds a Rust path *behind* the
   existing Python implementation. The Python fallback stays until the native path is
   proven in the wild, then is removed as a separate, deliberate change.
2. **Coarse boundaries.** Hand Rust a whole task; never set up Rust→Python callback
   loops. One call in, one finished result out.
3. **Measure before and after.** A migration that isn't measurably faster isn't worth
   the maintenance cost of two implementations. Capture a baseline first (see
   "Benchmarking" below).
4. **Mockable I/O.** All shell/HTTP access in Rust goes through the `SysInterface`
   trait so logic is unit-testable without a live system. Extend the trait rather than
   calling `std::process` / `ureq` directly from logic code.
5. **One gem deep before going wide.** Arch is the proving ground. Generalize a
   primitive into shared Rust only after a second consumer actually needs it.

---

## What's already done

- ✅ Rebrand bauh → Atlas (namespaces, config paths, UI strings).
- ✅ Qt5 UI purged; pywebview front-end in place.
- ✅ `atlas_rs` scaffolding: PyO3 + setuptools-rust build (`debug=False`).
- ✅ `map_srcinfo` — native `.SRCINFO`/pacman field parser (~2×), with Python fallback.
- ❌ Native pacman info parser, AUR RPC client, and DFS dependency resolver were built,
  measured, and **removed** (2026-05-29) — I/O-bound or marshalling-bound. See the
  VERDICT banner above and [STATUS.md](./STATUS.md).

---

## Prioritization model

Each candidate is scored on **Impact** (how much wall-clock time / responsiveness it
buys a typical user) and **Effort** (risk + lines + I/O surface). Hot paths = high
impact. We do high-impact/low-effort first, defer high-effort/low-impact.

| # | Candidate | Impact | Effort | Why it's hot |
|---|-----------|:------:|:------:|--------------|
| P0 | Harden the existing boundary | High | Low | Silent `except Exception` hides Rust regressions; the resolver isn't trustworthy until failures are visible & benchmarked. |
| P1 | Arch update detection (`updates.py`) | High | Med | Runs on every "check for updates"; compares installed vs repo+AUR versions across the whole system. Heavy parsing + version compares. |
| P2 | pacman output parsing (remaining `pacman.py`) | High | Med | Called constantly (`-Qi`, `-Si`, `-Qq`, search). Pure string-crunching — ideal for Rust. |
| P3 | Version comparison + dependency expr matching | High | Low | `vercmp`-style logic hit in tight loops by P1/P2/resolver. Small, pure, high-leverage, reusable. |
| P4 | AUR index build/search (`worker.py`) | Med | Med | Large in-memory index; fuzzy/substring search over thousands of names. |
| P5 | Package sorting / install ordering (`sorting.py`) | Med | Low | Topological/priority sort; partly already in the resolver — consolidate. |
| P6 | Concurrency layer (shared executor) | Med | Med | Python-side: stop blocking the UI; not Rust, but a prerequisite for perceived speed. |
| P7 | Shared Rust core extraction | Med | Med | Promote `SysInterface`, version compare, parsing into a reusable layer once ≥2 gems consume them. |
| P8 | Other gems (Flatpak/Snap/AppImage) hot paths | Low–Med | High | Each is lighter than Arch; revisit after Arch is fully native. |

---

## Phased plan

### Phase 0 — Harden & instrument the boundary  ✅ *(complete, 2026-05-28)*
**Goal:** make the native path trustworthy and measurable before adding more of it.

- ✅ Replaced blanket `except Exception: pass` with logging gated on `ATLAS_RS_DEBUG`
  (via `atlas/gems/arch/native.py`), so native regressions surface.
- ✅ Added `ATLAS_DISABLE_RS=1` to force Python-only for A/B testing and triage.
- ✅ Benchmark harness `benchmarks/bench_srcinfo.py` (deterministic A/B vs the original
  Python parser).
- ✅ Expanded `resolver.rs` / `pacman.rs` unit tests with mocked `SysInterface`
  (cargo tests 4 → 13).
- ➕ (bonus) Fixed a `deps_data` schema mismatch that crashed the native success path,
  and a build bug where `pip install -e .` shipped a *debug* extension.

**Key finding:** a debug `atlas_rs` ran ~4× **slower** than Python; the release build
runs ~2× **faster**. `setup.py` now pins `debug=False`. **Always benchmark release.**

### Phase 1 — Native Arch update detection  *(P1, P3)*
**Goal:** make "check for updates" near-instant on Arch.

- Port the installed-vs-available diff and version comparison out of `updates.py` into
  Rust. Pull P3 (version compare + dependency expression matching) in first as a
  standalone, well-tested primitive — the update check is its first heavy consumer.
- Reuse the existing `pacman.rs` parser and `aur.rs` client.
- Expose `check_arch_updates(...)` from `lib.rs`; wire into `updates.py` behind the
  fallback.

**Done when:** update detection is measurably faster and returns identical results to
the Python path on a real system.

### Phase 2 — Native pacman parsing consolidation  *(P2, on hold — see lesson)*
**Goal:** route pacman output parsing through `pacman.rs` *where it pays off*.

- ❌ `map_updates_data` (`pacman -Si`) was wired to a native parser and **reverted**: only
  ~1.2× (PyO3 result-marshalling dominates when returning many per-package dicts), not
  worth two implementations (2026-05-29).
- ⚠️ **Lesson:** parser ports only pay off for *small* results (`map_srcinfo` ~2×).
  Per-package dict results barely beat Python. Only revisit candidates here (search
  results, `-Qq` sets, file lists) if their result is compact, or fold parse+consume into
  one coarse Rust op that returns a small answer.

### Phase 3 — AUR index & search  *(P4, P5)*
**Goal:** fast suggestions/search and final consolidation of sorting.

- Build/load the AUR name index in Rust; expose native substring/fuzzy search.
- Fold `sorting.py`'s remaining ordering logic into the resolver's topological pass so
  there is one source of truth for install order.

### Phase 4 — Concurrency & UI responsiveness  *(P6)*
**Goal:** the UI never blocks regardless of backend speed.

- Standardize background work in `AtlasApi` on a shared `ThreadPoolExecutor` (or
  asyncio) instead of ad-hoc threads.
- Implement **lazy gem preparation** in `GenericSoftwareManager`: initialize only
  enabled gems, only when their view is first requested (sub-second launch target).

### Phase 5 — Shared Rust core  *(P7)*
**Goal:** stop duplicating primitives per gem.

- Once a second gem needs them, extract `SysInterface`, version comparison, and generic
  parsing into a shared module/crate. Re-point Arch at the shared layer.

### Phase 6 — Other gems  *(P8)*
- Apply the same loop to Flatpak/Snap/AppImage hot paths, prioritizing whichever shows
  up worst in real-world profiling.

---

## Per-migration checklist

Follow this for every item, regardless of phase:

- [ ] Write `docs/plans/YYYY-MM-DD-<feature>-design.md` (boundary, payload schema).
- [ ] Write `docs/plans/YYYY-MM-DD-<feature>-implementation.md` (task-by-task).
- [ ] Capture a Python baseline benchmark.
- [ ] Implement Rust logic against `SysInterface` (no direct I/O in logic).
- [ ] Add Rust unit tests with a mocked `SysInterface`.
- [ ] Expose via PyO3 in `lib.rs` and register in the `#[pymodule]`.
- [ ] Wire into the owning Python module **behind the existing fallback**.
- [ ] Verify identical results Rust vs Python on a real system.
- [ ] Record the measured speedup; commit with the established message convention.
- [ ] (Later, separately) remove the Python fallback once proven.

---

## Benchmarking

Keep a fixed, reproducible workload (a representative set of installed + AUR packages)
and time both paths via the `ATLAS_DISABLE_RS` switch. Record results in each plan doc
so the migration's value is on the record. Speedup claims without a number don't count.

---

## Risks & how we manage them

| Risk | Mitigation |
|------|-----------|
| Native path diverges from Python results | Keep fallback; A/B compare outputs in CI/manual verify before removing fallback. |
| Silent Rust failures masked by `except` | Phase 0 logging + force-disable switch. |
| Build fragility (setuptools-rust, ABI) | Pin toolchain; the fallback keeps Atlas runnable even if the `.so` is missing. |
| Premature shared-core abstraction | Don't generalize until a second real consumer exists (Phase 5 gate). |
| Scope creep into a full rewrite | Hot paths only; non-hot Python code stays Python indefinitely if it isn't a bottleneck. |

---

## Python-side work (the new focus)

The boundary lessons above point away from more Rust and toward pure-Python wins that
have no marshalling cost and bigger UX impact. From the original rebrand design doc:

### Faster launch — lazy gem init + concurrency ✅ *(already implemented)*
Verified 2026-05-29 — this was largely done already:

- ✅ **Lazy gem preparation:** `GenericSoftwareManager.prepare()` only runs the config
  step eagerly; managers are prepared on first use via `_ensure_prepared`/`_can_work`
  (per-manager locks). Tested in `tests/view/webview/test_lazy_load.py`.
- ✅ **Background prepare off the UI thread:** `AtlasApi` uses a shared
  `ThreadPoolExecutor(max_workers=5)` and submits `_prepare_manager`.
- ⚠️ **Optional remainder:** the controller still spawns ad-hoc `Thread(...)` for
  search/read-installed/suggestions. Routing those through a shared pool is low-value /
  higher-risk — only do it with a measured reason.

Still worth doing: a **launch-time baseline** (manually run `atlas`, measure
time-to-window and time-to-first-view). There's no automated GUI test.
