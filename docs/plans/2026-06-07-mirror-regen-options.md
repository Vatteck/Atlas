# Mirror regenerate options (country / protocol / sort)

**Date:** 2026-06-07
**Backlog item:** "Mirror manager polish → *possible follow-ups:* country/protocol regenerate
options" (BACKLOG §Arch utility cockpit).
**Status:** in progress.

## Goal

Settings → Mirrors currently regenerates `/etc/pacman.d/mirrorlist` with a **fixed** reflector
command (`--protocol https --latest 20 --sort rate`). Let the user choose a **country**, one or
more **protocols**, and a **sort** order before regenerating, with the previewed command updating
live so nothing is hidden (Atlas's "honest enough for Arch people" angle).

Scope is deliberately small and **reflector-only** — `rate-mirrors` (the fallback tool) doesn't
take the same flags, so when it's the active tool we keep the existing fixed command and don't show
the option controls.

## Design

### Backend (`atlas/view/webview/api.py`)

- **Curated country list** — a module/class constant `_MIRROR_COUNTRIES` of `{code, name}` (~40
  common Arch mirror countries; reflector accepts ISO-3166 codes via `--country`). No network call
  (reflector's `--list-countries` would be slow + needs reflector installed); a static list is the
  cheap, offline-friendly choice, same spirit as the curated category buckets.
- **`_sanitize_mirror_options(options)`** — pure, returns a normalized, **validated** dict
  `{country, protocols, sort, latest}`. Security matters: these flow into a *root* subprocess argv.
  Even though it's an argv list (no shell), we still whitelist hard:
  - `country`: `''` (Auto) or a code present in `_MIRROR_COUNTRIES`; anything else → `''`.
  - `protocols`: subset of `{'https','http','rsync'}`, order-preserved, deduped; empty → `['https']`.
  - `sort`: one of `{'rate','age','score','delay','country'}`; else `'rate'`.
  - `latest`: int clamped to `[5, 50]`; non-int → `20`.
- **`_mirror_regen_cmd(options=None)`** — gains an `options` arg. reflector argv built from the
  sanitized options:
  `reflector [--country CC] --protocol p1,p2 --latest N --sort S --download-timeout 5 --save <path>`.
  rate-mirrors branch unchanged (ignores options).
- **`get_mirror_status(options=None)`** — unchanged read of the file; the `command` preview is now
  built from `options`. When the tool is reflector it additionally returns `countries`
  (the curated list), `options` (the normalized current selection), `sorts` and `protocols`
  (available choices) so the frontend can render controls; omitted for rate-mirrors / no tool.
- **`preview_mirror_command(options)`** — new, cheap (no file read): returns `{status, command}`
  for the live preview as the user changes selectors. Fails open (no tool → `command: None`).
- **`regenerate_mirrorlist(options=None)`** — passes `options` through to `_mirror_regen_cmd`.
  Everything else (root broker, failure reporting) unchanged.

### Frontend (`atlas/view/webview/main.js`)

- **`buildMirrorOptionsHTML(mirror)`** — pure (Node-VM-tested): renders a country `<select>`
  (Auto + curated list, current selected), protocol checkboxes (https/http/rsync), and a sort
  `<select>`. Returns `''` when `mirror.options` is absent (rate-mirrors / no tool) so those setups
  keep the plain button. `latest` stays internal (default 20; not exposed — matches the mockup).
- **`readMirrorOptionsFromDOM()`** — gathers the current selections from the controls.
- Wiring in `renderSettings`: on any control change, recompute the previewed command via
  `preview_mirror_command` and update the `<code>` + the Copy-command button; persist the options to
  `localStorage` (`atlas_mirror_opts`). On load, seed the controls from that pref and pass it to the
  initial `get_mirror_status` so the preview matches.
- `regenerateMirrors(btn, options)` + the Settings regen handler pass the gathered options.

### Tests

- `test_api.py::MirrorOptionsTest` — `_sanitize_mirror_options` (defaults, whitelisting,
  clamp, dedupe), `_mirror_regen_cmd` argv reflects options, `get_mirror_status` exposes
  countries/options only for reflector, `preview_mirror_command` builds the command + fails open,
  `regenerate_mirrorlist(options)` passes the flags into the root subprocess argv.
- `main_js_contracts` — `buildMirrorOptionsHTML` (controls + selected state present for reflector,
  empty for rate-mirrors).

## Non-goals

- No rate-mirrors option mapping (different flags; keep its fixed command).
- No multi-country select (single dropdown; reflector *can* take a comma list, but the UI stays one).
- No `--age`/custom flag free-text (whitelist only).
