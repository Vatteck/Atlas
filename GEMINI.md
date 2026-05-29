# GEMINI.md

> For Gemini CLI and Antigravity.

The canonical operating manual for this project is **[AGENTS.md](AGENTS.md)** — read it
first, in full, before writing any code. It applies to all agents (Claude, Codex,
Gemini/Antigravity) so there is a single source of truth and no drift between tools.

## Before you start, read in this order
1. [AGENTS.md](AGENTS.md) — guardrails + workflow (canonical)
2. [docs/STATUS.md](docs/STATUS.md) — the live baton: where the project is right now
3. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system map + Python↔Rust boundary
4. [docs/ROADMAP.md](docs/ROADMAP.md) — what gets built next

## Non-negotiables (full list in AGENTS.md §3)
- Strangler-fig migrations only — add Rust **behind** the existing Python, never big-bang.
- Never delete a Python fallback in the same change that introduces its Rust path.
- Keep the Python↔Rust boundary coarse (one task in, one result out — no callback loops).
- Hot paths only; do not rewrite non-bottleneck code.
- No I/O in Rust logic — go through the `SysInterface` trait.
- Write a design + implementation plan in `docs/plans/` before non-trivial work.
- Do not reintroduce Qt; the UI is pywebview.

## When you finish
Follow the session-end handoff protocol in AGENTS.md §8 — update `docs/STATUS.md` so the
next agent (possibly a different model) picks up cleanly.
