# AUR suggestions support — design

**Date:** 2026-06-01
**Status:** implemented
**Type:** Python (Arch gem). No Rust, no Qt.

## Problem

`ArchManager.list_suggestions` filters suggestion names against
`pacman.map_available_packages()` (official repos only), so AUR-only names never surface —
even though `atlas-files` carried curated AUR picks. The suggestions panel is repo-only.

## Approach (single source, resolve per name)

Keep **one** suggestions file (`atlas-files/main/arch/suggestions.txt`) holding both repo
and AUR names. The downloader's cache path is class-level, so a second AUR downloader would
collide on the same file — hence one file, and `list_suggestions` decides repo-vs-AUR per
name:

1. Build repo suggestions as today (names present in `map_available_packages`).
2. If AUR is supported (`aur.is_supported`), take the suggestion names **not** in the repos
   (and not ignored) and resolve them in **one batched** `aur_client.get_info(names)` call.
   For each result, add `{'v': Version, 'r': 'aur', 'i': installed?, 'desc': Description}` to
   `available_suggestions` (installed check via `pacman.map_installed`, only when
   `filter_installed`).
3. The existing sort/limit/build loop then handles both. `pacman.map_packages` is called
   with **repo names only** (it can't resolve AUR names); AUR descriptions come from the
   stored `desc`.

Net cost: one extra batched AUR API call, only for the non-repo names, only when AUR is on.

## Data

Merge the curated AUR picks into `arch/suggestions.txt` (the file the app reads). The
separate `aur/suggestions.txt` stays unused legacy.

## Tests

`tests/gems/arch/` — `list_suggestions` returns AUR suggestions for non-repo names
(mock `aur_client.get_info` + `pacman`), respects `filter_installed`, and skips AUR
resolution when AUR is unsupported.
