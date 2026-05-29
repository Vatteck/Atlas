# AGENTS.md — Operating Manual for AI Coding Agents

**This is the canonical context file for any AI agent working on Atlas** (Claude Code,
Codex/GPT, Antigravity/Gemini, Cursor, etc.). `CLAUDE.md` and `GEMINI.md` just point
here. Read this top to bottom before writing code. It takes ~2 minutes and keeps you on
the project's trajectory.

> Atlas is **vibecoded across multiple agents**. You will not have the previous agent's
> memory. These docs *are* the memory. Trust them, keep them current, and follow the
> guardrails — they exist because the project's value depends on staying consistent
> across handoffs.

---

## 1. Bootstrap — read these in order

1. **This file** (guardrails + workflow). ← you are here
2. **[`docs/STATUS.md`](docs/STATUS.md)** — the live baton: what just shipped, what's
   next, known gaps. *Always read this to know where the project actually is right now.*
3. **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** — the system map and the
   Python↔Rust boundary rules.
4. **[`docs/ROADMAP.md`](docs/ROADMAP.md)** — what gets built next and in what order.
5. **[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)** — build / run / test commands.
6. **[`docs/atlas_rs-API.md`](docs/atlas_rs-API.md)** — the native module surface.

Do not start coding until you've read 1–4. If the user's request conflicts with the
roadmap, say so and ask — don't silently go off-plan.

---

## 2. What Atlas is (the 30-second version)

- Atlas (formerly **bauh**) is an All-In-One Linux package manager GUI: AppImage,
  Arch/AUR, Debian, Flatpak, Snap, native Web apps.
- It's a **Python application** (`atlas/`) with a **pywebview** front-end, undergoing two
  transitions: Qt5 → webview UI (done), and pure-Python engine → **Rust hot paths via
  PyO3** (in progress, the `atlas_rs` crate in `rust/`).
- The active work is rewriting the **Arch dependency/engine hot paths in Rust**, hot
  paths first, one strangler-fig step at a time.

---

## 3. Golden rules (the guardrails) — do not violate without explicit user sign-off

1. **Strangler fig, never big-bang.** Add a Rust path *behind* the existing Python
   implementation. Try Rust first, fall back to Python on any failure.
2. **Never delete a Python fallback in the same change that adds its Rust path.**
   Fallbacks are removed later, deliberately, only once the native path is proven.
3. **Keep the Python↔Rust boundary coarse.** Hand Rust a whole task; get one finished
   result back. No Rust→Python callback loops, no chatty fine-grained calls.
4. **Hot paths only.** We migrate slow, CPU/IO-heavy code. Non-bottleneck Python stays
   Python — do not rewrite things just because you can.
5. **No I/O in Rust logic.** Shell/HTTP access goes through the `SysInterface` trait
   (`rust/src/sys.rs`) so logic stays unit-testable with mocks. Extend the trait; don't
   call `std::process`/`ureq` from logic code.
6. **Plan before non-trivial work.** Any backend/Rust change gets a design doc + an
   implementation plan in `docs/plans/` *before* implementation (see §5).
7. **Do not reintroduce Qt.** The Qt5 UI was purged. The UI is pywebview
   (`atlas/view/webview/`). Anything importing Qt forms/widgets is dead.
8. **Verify, don't assume.** This codebase carries inaccurate-sounding legacy strings.
   Before acting on a file/function/flag, confirm it still exists and does what you think.
9. **Measure migrations.** A Rust rewrite that isn't measurably faster isn't worth two
   implementations. Capture a baseline; quote the speedup.
10. **Update the baton.** Before you finish a session, update `docs/STATUS.md` (see §8).
    This is how the next agent — maybe a different model — picks up cleanly.

---

## 4. Where things live

```
atlas/                      Python application
  app.py                    entry points: main (GUI), tray, cli
  api/abstract/             SoftwareManager ABC + shared contracts
  view/core/controller.py   GenericSoftwareManager (orchestrator)
  view/webview/             pywebview front-end + AtlasApi bridge
  gems/<type>/              one backend per package type (arch is the focus)
  commons/                  shared utilities (version_util, ...)
rust/                       atlas_rs crate (PyO3): lib.rs, sys.rs, pacman.rs, aur.rs, resolver.rs
docs/                       ARCHITECTURE, ROADMAP, DEVELOPMENT, atlas_rs-API, STATUS, plans/
```
Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 5. The migration workflow (follow this for every backend/Rust change)

1. Write `docs/plans/YYYY-MM-DD-<feature>-design.md` — state the boundary + payload schema.
2. Write `docs/plans/YYYY-MM-DD-<feature>-implementation.md` — task-by-task, with the
   verify + commit step for each task.
3. Capture a Python baseline benchmark for the workload you're speeding up.
4. Implement Rust logic against `SysInterface`.
5. Add Rust unit tests with a mocked `SysInterface`.
6. Expose via PyO3 in `rust/src/lib.rs` and register in the `#[pymodule]` block.
7. Wire into the owning Python module **behind the existing fallback**.
8. Verify identical results native vs Python on a real system; record the speedup.
9. (Later, separately) remove the Python fallback once proven.

The full checklist is in [`docs/ROADMAP.md`](docs/ROADMAP.md#per-migration-checklist).

---

## 6. Build / run / test (quick reference)

```bash
# setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt setuptools-rust

# build the Rust extension (rerun after editing rust/src/*)
pip install -e .                                  # builds atlas_rs into atlas/gems/arch/
cargo check --manifest-path rust/Cargo.toml       # fast Rust type-check during iteration

# run
atlas --logs            # GUI    (or: python -m atlas.app --logs)
atlas-cli               # CLI

# test
python -m pytest
cargo test --manifest-path rust/Cargo.toml        # uses a mocked SysInterface
```

⚠️ If you edit `rust/src/*` and don't rerun `pip install -e .`, your changes won't take
effect and Atlas will silently keep using the old `.so` (or the Python fallback). Full
notes + pitfalls in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

---

## 7. Conventions

- **Python:** PEP 8. **Rust:** `cargo fmt`.
- **Commits:** conventional prefixes already in use — `feat:`, `fix:`, `refactor:`,
  `docs:`, `chore:`, `test:`. One logical change per commit.
- **Structured Rust→Python results:** a `dict` with a `status` discriminator
  (`"success"` / `"needs_providers"` / ...). See the API doc.
- **Branch:** work lands on `master`; spin up a short-lived branch for a larger feature
  and merge it back when done. Check `git branch` for what's currently active rather than
  assuming — branch names in docs go stale fast.

---

## 8. Session-end handoff protocol (do this before you stop)

You are probably handing off to a different agent that won't remember this session.
Leave the baton in good shape:

1. Update **[`docs/STATUS.md`](docs/STATUS.md)**: move finished items to "Done", set the
   new "Current focus" and "Next", and add any new gotcha to "Known gaps".
2. If you started a feature, ensure its `docs/plans/` design + implementation docs reflect
   reality (update them if you deviated).
3. Make sure the tree builds (`cargo check` + `pip install -e .`) and tests pass, or note
   clearly in STATUS.md what's broken and why.
4. Commit with a clear message. Don't leave half-applied edits without a note.

If you only did exploration/answered a question and changed no code, you don't need to
touch STATUS.md.

---

## 9. Known sharp edges (read before touching the Arch engine)

These are real and easy to trip on — also tracked in `docs/STATUS.md`:

- The native `map_missing_deps` fallback uses `except Exception: pass`, which **hides
  Rust bugs as "slow but works."** Run with the debug switch (being added in Roadmap
  Phase 0) before trusting the native path.
- `map_missing_deps` does **not yet wire `choices`/`providers_repos`** out to Python, so
  the native path only handles `status == "success"`. See `docs/atlas_rs-API.md`.
- `controller.py` (~192 KB), `updates.py` (~42 KB), `pacman.py` (~38 KB) are large; read
  the relevant section, don't try to hold the whole file in your head.
