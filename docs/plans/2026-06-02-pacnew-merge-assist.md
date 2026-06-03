# `.pacnew` merge assist — 2026-06-02

## Goal

Atlas already *detects* `.pacnew`/`.pacsave` files on the Updates view (`get_pacnew_files` +
`renderUpdatesNotice`) and tells the user to run `sudo pacdiff`. This adds a **button** that
launches `pacdiff` for them in a real terminal.

## Why a real terminal (not the in-app panel)

`pacdiff` is **interactive** — it prompts per file (view/merge/remove) and runs a diff/merge tool
(vimdiff by default). The in-app terminal panel streams output but isn't an interactive TTY, so
pacdiff needs an actual terminal-emulator window.

## Backend (`atlas/view/webview/api.py`)

- `_find_terminal()` → the argv prefix of an available terminal emulator, honoring `$TERMINAL`
  first, then a curated priority list of emulators whose exec-flag takes the command as
  **separate args** (so we don't have to shell-quote): `konsole -e`, `gnome-terminal --`,
  `alacritty -e`, `kitty`, `foot`, `wezterm start --`, `xfce4-terminal -x`, `xterm -e`. Returns
  None if none found.
- `launch_pacdiff()`:
  - `pacdiff` missing (`shutil.which`) → error: "install pacman-contrib".
  - no terminal found → error: "run sudo pacdiff manually".
  - else `subprocess.Popen([*term, 'sudo', 'pacdiff'], start_new_session=True)` (detached, owns
    its own TTY — we don't capture output) → `{status: ok}`.
  - Single `sudo` prompt up front (run the whole thing as root) — matches the existing notice text.

## Frontend (`main.js` / `style.css`)

- Add an "Open pacdiff in a terminal" button to the `.pacnew` notice in `renderUpdatesNotice`,
  wired to `pyApiCall('launch_pacdiff')`; toast on success, the backend error toast on failure
  (no terminal / pacdiff not installed). A `.config-notice-actions` style for the button row.

## Tests (`tests/view/webview/test_api.py`)

- `launch_pacdiff`: pacdiff-missing → error; no-terminal → error; success → `Popen` called with
  `[…term…, 'sudo', 'pacdiff']` and `start_new_session=True`. (Mock `shutil.which` + `subprocess.Popen`,
  clear `$TERMINAL`.)

## Notes

- Read-only/no-merge from Atlas itself — we just launch the standard tool; the user does the merge
  in pacdiff. No content reads, no auto-removal (keeps with the existing detect-and-list stance).
