# AGENTS.md — Operating Manual for AI Coding Agents

**This is the canonical context file for any AI agent working on Atlas** (Claude Code,
Codex/GPT, Antigravity/Gemini, Cursor, etc.). `CLAUDE.md` and `GEMINI.md` just point
here. Read it top to bottom before writing code — it keeps you on the project's trajectory.

> Atlas is **vibecoded across multiple agents**. You will not have the previous agent's
> memory. These docs *are* the memory. Trust them, keep them current, and follow the
> guardrails — the project's value depends on staying consistent across handoffs.

---

## 1. Bootstrap — read these in order

1. **This file** (guardrails + workflow). ← you are here
2. **[`docs/STATUS.md`](docs/STATUS.md)** — the live baton: what just shipped, what's
   next, known gaps. *Always read this to know where the project actually is right now.*
3. **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** — the system map.
4. **[`docs/ROADMAP.md`](docs/ROADMAP.md)** — what gets built next.
5. **[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)** — build / run / test commands.

Do not start coding until you've read 1–4. If the user's request conflicts with the
roadmap, say so and ask — don't silently go off-plan.

---

## 2. What Atlas is (the 30-second version)

- Atlas (a fork of **[bauh](https://github.com/vinifmor/bauh)**) is an **Arch-focused**
  all-in-one package manager GUI. Primary sources: **official Arch repos, AUR, Flatpak,
  AppImage**. (Snap, Debian, and native Web apps still exist as gems but are **off by
  default** — re-enable in Settings.)
- It is a **pure-Python application** (`atlas/`) with a **pywebview** front-end
  (`atlas/view/webview/`) and one backend "gem" per package type (`atlas/gems/<type>/`).
- Two past transitions are **done**: Qt5 → pywebview UI, and a Rust-hot-paths experiment
  that was **removed** (see §3.2 and the Rust verdict in ROADMAP) — Atlas is plain Python
  again, no native extension.

---

## 3. Golden rules (the guardrails) — do not violate without explicit user sign-off

1. **Arch-focused.** The four first-class sources are Arch repo, AUR, Flatpak, AppImage.
   Keep Arch and AUR visibly distinct (AUR is community-maintained / less vetted). Don't
   re-enable Snap/Debian/Web by default.
2. **Don't reintroduce Rust (or Qt) without sign-off.** The Qt5 UI was purged (UI is
   pywebview). The Rust `atlas_rs` extension was removed because a package manager is
   I/O-bound, not CPU-bound — only port to a native lang if you have a *measured*
   CPU-bound hot path with a small result, and get the user's OK first.
3. **Strangler-fig risky changes.** For a behavioural rewrite, add the new path, keep the
   old one as a fallback, prove the new one, then remove the old — in separate steps.
4. **Plan before non-trivial work.** Backend/engine changes get a short design +
   implementation note in `docs/plans/YYYY-MM-DD-<feature>.md` *before* you implement.
5. **Verify, don't assume.** This codebase carries inaccurate-sounding legacy strings.
   Before acting on a file/function/flag, confirm it still exists and does what you think.
6. **Measure.** Don't add complexity (caches, threads, native code) without a measured
   reason; quote the before/after.
7. **Update the baton.** Before you finish a session, update `docs/STATUS.md` (see §7).

---

## 4. Where things live

```
atlas/                      Python application
  app.py                    entry points: main (GUI), cli
  api/abstract/             SoftwareManager ABC + shared contracts
  view/core/controller.py   GenericSoftwareManager (orchestrator)
  view/webview/             pywebview front-end: index.html, main.js, style.css, api.py, watcher.py
  gems/<type>/              one backend per package type (arch is the focus)
  commons/                  shared utilities (version_util, config, system, ...)
docs/                       ARCHITECTURE, ROADMAP, DEVELOPMENT, STATUS, plans/
```
Runtime data (suggestions, categories, AppImage DB, web env) lives in the separate
**[Vatteck/atlas-files](https://github.com/Vatteck/atlas-files)** repo, fetched from its
`main` branch. Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 5. Build / run / test (quick reference)

```bash
# system deps (Arch): python gtk3 webkit2gtk python-gobject git
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e .                  # plain setuptools — no Rust/cargo

# run
atlas --logs            # GUI    (or: python -m atlas.app --logs)
atlas-cli               # CLI

# test
python -m pytest
```

The webview is **WebKitGTK** — it has no native `window.prompt/confirm/alert`; all dialogs
are HTML modals driven from `atlas/view/webview/`. Full notes in
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

---

## 6. Conventions

- **Python:** PEP 8.
- **Commits:** conventional prefixes — `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`,
  `test:`. One logical change per commit. End commit messages with the
  `Co-Authored-By:` trailer.
- **Branches:** Atlas app work lands on `master`; the `atlas-files` repo uses `main`. Check
  `git branch` rather than assuming — branch names in docs go stale.

---

## 7. Session-end handoff protocol (do this before you stop)

You are probably handing off to a different agent that won't remember this session.

1. Update **[`docs/STATUS.md`](docs/STATUS.md)**: move finished items to "Done", set the
   new "Current focus"/"Next", add any new gotcha to "Known gaps".
2. If you started a feature, make sure its `docs/plans/` note reflects what you actually did.
3. Make sure the tree imports and tests pass (`python -m pytest`), or note clearly in
   STATUS.md what's broken and why.
4. Commit with a clear message. Don't leave half-applied edits without a note.

If you only answered a question / changed no code, you don't need to touch STATUS.md.

---

## 8. Known sharp edges

Tracked in more detail in `docs/STATUS.md`:

- **WebKitGTK has no native JS dialogs.** `window.prompt/confirm/alert` no-op; everything
  is HTML modals that block a pywebview worker thread on a `threading.Event` and resolve
  via `js_api` callbacks. Never reintroduce a `window.*` dialog.
- **Large files — read in sections:** `view/core/controller.py` (~192 KB), `gems/arch/
  controller.py`, `updates.py` (~42 KB), `pacman.py` (~38 KB).
- **Settings are webview-native.** The GUI uses `AtlasApi.get_app_settings`/
  `save_app_settings`, *not* the old Qt-era `GenericSettingsManager` tree.
