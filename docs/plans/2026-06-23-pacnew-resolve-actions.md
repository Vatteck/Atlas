# In-app .pacnew resolution: Discard / Apply

**Date:** 2026-06-23
**Status:** implementing

## Problem

The Updates notice and the `.pacnew` center warn about pending `.pacnew`/`.pacsave`
files and recommend actions ("review with pacdiff, then remove the `.pacnew`"; for
mirrorlist "just discard the `.pacnew`"). But the only way to *act* on that advice was to
drop into a terminal via `pacdiff`. There was no in-app way to even delete a `.pacnew`.

## Decision

Add the two safe, terminal-free, root-only per-file actions to the `.pacnew` center:

- **Discard `.pacnew`** — `rm -f <path>`, keeping the current config. Directly fulfils
  the "just discard" advice. Available for every file (incl. mirrorlist).
- **Apply (overwrite)** — `mv <path> <base>`, replacing the live config with the new
  default. For people who never customised the file. **Hidden for `mirrorlist`** (the
  `.pacnew` is the stock all-commented list; applying it wipes mirrors — regenerate
  instead). Confirmed first; warns harder on critical files.

Deliberately **not** building an in-app line-by-line merge editor — that rebuilds
`pacdiff` inside WebKitGTK (large privileged surface, ongoing maintenance). `pacdiff` in
a terminal stays the path for true merges.

## Implementation

### Backend — `atlas/view/webview/api.py`

Two methods next to `launch_pacdiff`. Both:
- whitelist `path` against `get_pacnew_files()` (no arbitrary file ops),
- require the path to end in `.pacnew`/`.pacsave`,
- run as root via `ensure_root_password()` + `new_root_subprocess(...)`,
- return `{status:'ok'}` / `{status:'cancelled'}` / `{status:'error', message}`.

`discard_pacnew(path)` → `rm -f <path>`.
`apply_pacnew(path)` → refuse when base name is `mirrorlist`; else `mv -f <path> <base>`
(atomic same-filesystem replace; preserves nothing fancy — pacman's `.pacnew` is the
intended replacement file).

### Frontend — `atlas/view/webview/main.js`

In `renderPacnewCenter` rows add per-file buttons. Apply omitted for mirrorlist. Each
confirms via `prompt_confirmation`, calls the API, toasts, and re-renders the center
(which also refreshes the Updates notice badge on next visit).

## Out of scope / risk notes

- No merge editor.
- Apply on a customised file loses customisations — that's why it confirms and the diff
  is one click away in the same row.
- mirrorlist Apply is blocked in both UI and backend (defence in depth).
