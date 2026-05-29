# CLAUDE.md

The canonical operating manual for this project is **[AGENTS.md](AGENTS.md)** — read it
first. It applies to all agents (Claude, Codex, Gemini/Antigravity).

@AGENTS.md

## Quick reminders for Claude Code

- Always read **[docs/STATUS.md](docs/STATUS.md)** at the start of a session to see where
  the project actually is.
- Follow the golden rules in AGENTS.md §3 — especially: strangler-fig migrations, never
  delete a Python fallback in the same change that adds its Rust path, keep the
  Python↔Rust boundary coarse, and write a plan in `docs/plans/` before non-trivial work.
- After making changes, follow the session-end handoff protocol in AGENTS.md §8 (update
  `docs/STATUS.md`).
