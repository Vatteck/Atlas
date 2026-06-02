# Maintenance / Cleanup hub

**Date:** 2026-06-01
**Status:** done (2026-06-02)
**Scope:** turn the **Disk** view from informational into actionable — a "Reclaim space"
panel that surfaces and clears the three big Arch space-wasters, each with a size estimate
and a confirm step.

## Why
The Disk view already computes per-package sizes (`get_disk_usage`) and we already have
orphan detection (`get_orphans` / `get_orphan_count`). The obvious next step is to let the
user *act* on disk pressure without dropping to a terminal. Three sources, in order of
value/safety:

1. **Orphan packages** — already shipped (the `cleanup-orphans-btn` checklist). Fold it
   into the panel visually; no backend change.
2. **pacman package cache** (`/var/cache/pacman/pkg`) — grows unbounded. `pacman -Sc`
   drops cached tarballs for packages that are *no longer installed* (keeps installed
   ones so downgrades still work). Precise, well-understood, Arch-only.
3. **Unused Flatpak runtimes** — `flatpak uninstall --unused` removes runtimes/extensions
   nothing references.

## Backend (`atlas/view/webview/api.py`)

New constant `PACMAN_CACHE_DIR = '/var/cache/pacman/pkg'`. New imports: `os`, `shutil`,
and from `commons.system`: `run_cmd`, `new_subprocess`, `new_root_subprocess`,
`get_dir_size`.

- **`get_cleanup_summary() -> dict`** — cheap, read-only, **no `read_installed()`** so it's
  fast enough to call when the Disk view opens. Returns:
  ```jsonc
  {"status":"ok","data":{
     "orphans": {"count": N},                         // pacman -Qtdq (reuse list_orphans)
     "pacman_cache": {"available": true,
                      "total_bytes": .., "total_human": "..",
                      "removable_bytes": .., "removable_human": ".."},
     "flatpak": {"available": true}                   // flatpak present + gem enabled
  }}
  ```
    Note: the summary reports **total** cache size only, not a reclaimable estimate —
    `pacman -Sc --print` needs root (verified on the dev box: it errors "you cannot
    perform this operation unless you are root"), so a cheap, no-prompt estimate isn't
    possible. We report the *actual* freed amount after cleaning instead (below).
- **`clean_pacman_cache() -> dict`** — `ensure_root_password()` (returns `cancelled` if the
  user backs out), measure `get_dir_size(cache)` **before**, run
  `new_root_subprocess(['pacman','-Sc','--noconfirm'], pwd)`, `.communicate()`, check
  returncode, measure size **after**; `freed_bytes = max(0, before-after)`. Fires `_notify`.
- **`clean_flatpak_unused() -> dict`** — honour the configured install level
  (`flatpak_man.configman.get_config().get('installation_level')`): `system` →
  `--system` under root; anything else → `--user` (no root). Runs
  `flatpak uninstall --unused --assumeyes <scope>`, checks returncode, `_notify`.

All three actions return `{'status': 'ok'|'error'|'cancelled', ...}`; errors carry a
`message` (decoded stderr). Nothing here calls `read_installed()`.

## Frontend (`index.html` / `main.js` / `style.css`)

- A **Maintenance panel** rendered at the top of the Disk view (in `renderDiskUsage`,
  before the existing summary card). Three rows: Orphans / Package cache / Flatpak
  runtimes — each shows its estimate (count or size) and a button, and hides/greys when
  there's nothing to do or the source is unavailable.
- Orphans row reuses the existing checklist flow (`get_orphans` → `prompt_confirmation`
  with checkboxes → `batch_uninstall`).
- Cache + Flatpak rows call `prompt_confirmation` (plain), then the respective clean
  action, then re-run `get_cleanup_summary()` + `renderDiskUsage()` and toast the result.
- Summary fetched via `get_cleanup_summary()` when the Disk view renders.

## Safety / guardrails
- `pacman -Sc` keeps cache for *installed* packages → downgrades still possible. (We are
  **not** using `-Scc`, which nukes everything.)
- Every destructive action is behind a confirm + the root broker; estimates are read-only.
- Flatpak cleanup scope matches the install level the app uses, so we don't surprise-prompt
  for root on a user-level setup.

## Tests (`tests/view/webview/test_api.py::CleanupHubTest`)
- `get_cleanup_summary` shape + that it does **not** call `read_installed` (mirror the
  existing `test_orphan_count_is_cheap` approach); + a no-cache/no-flatpak variant.
- `clean_pacman_cache`: `cancelled` when `ensure_root_password` yields None (and we never
  shell out); `error` on non-zero returncode; success reports `freed_bytes` = before−after
  (mock `get_dir_size` side_effect `[before, after]`) and fires `_notify`.
- `clean_flatpak_unused`: user level → `new_subprocess` with `--user`, **no** root prompt;
  system level → `new_root_subprocess` with `--system` and a root prompt.

## Out of scope (follow-ups)
- System *and* user Flatpak in one pass (we do the configured scope only).
- AUR build-dir cache (`~/.cache/yay`) cleaning.
- `paccache`-style "keep N versions of still-installed packages" (more aggressive).
