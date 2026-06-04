# GEMINI.md

> For Gemini CLI and Antigravity.

The canonical operating manual for this project is **[AGENTS.md](AGENTS.md)** — read it
first, in full, before writing any code. It applies to all agents (Claude, Codex,
Gemini/Antigravity) so there is a single source of truth and no drift between tools.

## Before you start, read in this order
1. [AGENTS.md](AGENTS.md) — guardrails + workflow (canonical)
2. [docs/STATUS.md](docs/STATUS.md) — the live baton: where the project is right now
3. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — current system map
4. [docs/BACKLOG.md](docs/BACKLOG.md) — longer-horizon feature/QoL menu
5. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — build / run / test commands
6. [docs/ROADMAP.md](docs/ROADMAP.md) — historical Rust verdict, not the active plan

## Non-negotiables (full list in AGENTS.md §3)
- Atlas is Arch-focused: Arch repos, AUR, Flatpak, and AppImage are first-class; Snap,
  Debian, and Web apps stay optional/off by default.
- Do not reintroduce Rust or Qt without explicit sign-off. Atlas is pure Python and the
  active UI is pywebview/WebKitGTK.
- Keep Arch official packages and AUR packages visibly distinct.
- Use strangler-fig migrations for risky behavior: add the new path, keep the old fallback,
  prove the new path, then remove the old one separately.
- Write a design + implementation plan in `docs/plans/` before non-trivial backend/engine work.
- Verify live behavior instead of trusting stale strings or legacy code comments.

## When you finish
Follow the session-end handoff protocol in AGENTS.md §7 — update `docs/STATUS.md` so the
next agent (possibly a different model) picks up cleanly.
