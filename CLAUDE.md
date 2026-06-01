# CLAUDE.md

The canonical operating manual for this project is **[AGENTS.md](AGENTS.md)** — read it
first. It applies to all agents (Claude, Codex, Gemini/Antigravity).

@AGENTS.md

## Quick reminders for Claude Code

- Always read **[docs/STATUS.md](docs/STATUS.md)** at the start of a session to see where
  the project actually is.
- Follow the golden rules in AGENTS.md §3 — especially: Atlas is Arch-focused and
  **pure-Python** (don't reintroduce Rust or Qt without sign-off), verify don't assume,
  and write a plan in `docs/plans/` before non-trivial work.
- After making changes, follow the session-end handoff protocol in AGENTS.md §7 (update
  `docs/STATUS.md`).
