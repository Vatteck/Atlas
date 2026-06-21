# Theme options — accent colors + preset palettes — 2026-06-20

Follow-on from the launch work. Two bugs surfaced while fixing the splash flash:
1. **localStorage didn't persist** (pywebview `private_mode`) — FIXED (theme/density/etc. now survive
   relaunch). See [2026-06-20-launch-optimization.md].
2. The native window background (the splash-flash color) is **hardcoded dark** — a non-dark theme
   would flash dark. This plan folds in the proper fix.

User decision: **Both** (accent picker + preset palettes, staged) and **fold in the
Python-readable theme mirror** so the flash color tracks the active theme.

## Current theming (what we build on)

- Pure CSS custom properties. `:root` = light palette; `[data-theme="dark"]` overrides. `main.js`
  flips `data-theme` on `<html>` and persists `atlas-theme` in localStorage (now durable).
- Accent = 5 vars: `--accent-color`, `--accent-hover`, `--accent-glass`, `--accent-shadow-hover`,
  `--accent-border-hover`. Base = bg/text/border vars.
- Settings render as `settings-row`s; density is the model (a `<select>` persisted to localStorage,
  applied immediately). Topbar has a binary `#theme-toggle`.

## Design

### Two independent axes
- **mode/palette** → `data-theme` (light, dark, + presets: nord, solarized-dark, midnight,
  high-contrast…). Each is a `[data-theme="x"]` block overriding the base vars.
- **accent** → new `data-accent` attribute on `<html>` (indigo[default], blue, teal, green, rose,
  amber). Each is a `[data-accent="x"]` block setting the 5 accent vars. Composes with any palette.
  Accent values chosen to read on both light and dark; the default keeps today's per-mode indigo
  when `data-accent` is unset/"indigo" (back-compat).

### Persistence + flash mirror (the key bit)
- `atlas-theme` and `atlas-accent` in localStorage (durable now) drive the live UI.
- On every theme/accent apply, `main.js` reads the resolved `--bg-base`
  (`getComputedStyle`) and sends it to a new `AtlasApi.set_window_bg(hex)` which stores it in the
  core config (`core['ui']['window_bg']`). **Theme-agnostic**: the flash color auto-tracks whatever
  base the active palette resolves to — Python never needs to understand theme semantics.
- `app.py` reads `config['ui']['window_bg']` (default `#05070c`) for `create_window(background_color=)`.
  First launch / unknown → dark default (today's behaviour).

### UI
- New **Appearance** settings section: a **Theme** `<select>` (Light, Dark, + presets) and an
  **Accent** swatch row (clickable color dots, selected ring). Both apply immediately + persist.
- Keep the topbar `#theme-toggle` as a quick light/dark flip (it just sets `data-theme`).

## Staging
- **Stage 1 (this pass):** accent picker + the persistence/flash mirror + Appearance section with
  Light/Dark. Pure CSS + main.js + one small API method + app.py read. Unit-testable bits: the
  accent/theme apply helpers (JS contract), the config read/write (py).
- **Stage 2:** add preset palettes (`[data-theme=...]` blocks) + populate the Theme select. Each
  preset needs a **GUI eyeball** (contrast/readability across the app).

## Risks / notes
- WebKitGTK CSS: stick to explicit values; avoid `color-mix()`/relative-color (uncertain support).
- Presets multiply the surface to eyeball; ship 2–3 good ones, not a dozen mediocre.
- `data-theme="dark"` is hardcoded on `<html>` in index.html as the pre-JS default — keep it so the
  first paint (before main.js) matches the dark window bg.
