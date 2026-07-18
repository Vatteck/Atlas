# Terminal pane: syntax highlighting + floating dialog — 2026-07-17

## Problem

1. The transaction terminal renders every log line in one flat color (green `#a8ff78`
   on `#0d1117`) — hard to scan, and errors/warnings don't stand out.
2. It's a right sidepane (480px, slides in) over a dimming overlay. The overlay already
   blocks navigation, but the sidepane *looks* like the app is still usable — Vatteck:
   "it makes me think I can keep navigating around the app, but you can't. And probably
   shouldn't until the work is done."

## Solution

**A) Per-line log highlighting** — new pure `highlightLogLine(line)` in main.js,
modeled on the existing `highlightBashLine` (regex-based, escapes its own input, no
external lib — WebKitGTK offline). Line-level classes mirror what the real tools do in
a color terminal:

- `tlog-error` — `==> ERROR:` / leading `error:` (bold red)
- `tlog-warn` — `==> WARNING:` / leading `warning:` (bold amber)
- `tlog-header` — makepkg `==>` section headers (bold green)
- `tlog-step` — makepkg `  ->` sub-steps (blue)
- `tlog-notice` — pacman `::` lines (bold blue)

Neutral/step lines additionally get safe whitespace-token inline highlighting
(no overlapping-replace corruption): URLs, absolute paths, `name-1.2.3-1` package
tokens, versions/sizes/percentages/`(n/m)` counters. Default text goes from green to
neutral `#c9d1d9`. `terminalAppend` switches from `textContent` to the highlighter's
HTML; the Copy-log buffer stays raw.

**B) Sidepane → centered floating dialog** — CSS-only (same DOM/ids/JS): the panel
becomes a centered modal (`min(720px, 94vw)` × `min(72vh, 680px)`, rounded, fade+scale
in) over the existing overlay. Rationale: the operation is already modal; a dialog says
so honestly, the sidepane didn't. Trivial to revert (one CSS block).

## Tests

`testHighlightLogLine` in `tests/view/webview/main_js_contracts.test.js` (hook export):
line classes for error/warning/header/step/notice, inline URL/path/version tokens,
HTML escaping of `<`/`&`, null/empty safety.

## Non-changes

- `watcher.py` protocol (`terminalOpen/Append/SetStatus/...`) untouched.
- Failure summary, activity line, progress bar, Copy log: untouched.
- No external highlight library (offline WebKitGTK, solo-dev maintenance).
