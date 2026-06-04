# 2026-06-04 — `.pacnew` center + mirror manager polish

Finishing the "Arch cockpit" (BACKLOG → Open work). Both build on existing backends.

## 1. `.pacnew` center

Promote the Updates-view `.pacnew` notice into a real, reviewable section.

- **Reachable** (no permanent nav item — it's usually empty): from the **System Health** "Config
  files (.pacnew)" card ("Review files") and from the **Updates notice** ("Review config files").
  Rendered as a sub-view (`currentView = 'pacnew'`, like a Browse category) with a back button.
- **Per file**: a **risk badge** + note (pure `pacnewRisk(path)`):
  - `mirrorlist` → **danger** ("overwriting wipes your mirror servers — regenerate instead").
  - `pacman.conf` / `sudoers` / `fstab` / `crypttab` / `mkinitcpio.conf` / `passwd`/`shadow`/`group`
    → **warn** ("review carefully — system-critical").
  - everything else → **info** ("review when convenient").
  - Actions per file: **Show diff** (toggle), **Copy path**.
- **Show diff**: backend `get_pacnew_diff(path)` runs `diff -u <base> <path>` (no root; base = path
  minus the `.pacnew`/`.pacsave` suffix), **whitelisted** to paths actually returned by
  `get_pacnew_files()` (no arbitrary read), truncated. Unreadable base (root-only) → a clear "needs
  root — use pacdiff" message.
- **Global actions**: **Open pacdiff** (existing `launch_pacdiff`), and **Regenerate mirror list**
  when `mirrorlist` is among the files. **No auto-merge / no delete** (we only launch the standard
  tool), matching the existing safety stance.
- `copyText(text)` helper: `navigator.clipboard` with a hidden-textarea + `execCommand('copy')`
  fallback (WebKitGTK may not expose the async clipboard).

## 2. Mirror manager polish (Settings → Mirrors)

- Backend `get_mirror_status()` → `{count, servers:[top 5 host strings], last_modified_iso, tool,
  command}` parsed from `/etc/pacman.d/mirrorlist` (active uncommented `Server = …` lines) + file
  mtime; `command` is the resolved regenerate argv joined (so we can preview it). Best-effort.
- Settings → Mirrors shows: **N active mirrors**, the **top few hosts**, **last updated** time, the
  **exact command** that will run (preview), then the existing **Regenerate** button. After a
  successful regenerate, the summary refreshes in place (re-render Settings).

## Tests

- `test_api.py` — `get_pacnew_diff` whitelist (rejects a path not in the pacnew list) + a real diff
  on a temp pair; `get_mirror_status` parsing (active vs commented lines, count, hosts).
- `main_js_contracts.test.js` — `pacnewRisk` (mirrorlist→danger, pacman.conf→warn, random→info).

## Verification

`python -m pytest` + Node harness green; **GUI eyeball** (open the center from Health/Updates, show a
diff, the mirror summary + command preview).
