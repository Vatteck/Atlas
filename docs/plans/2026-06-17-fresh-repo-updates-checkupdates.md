# Fresh repo-update detection via `checkupdates` — 2026-06-17

## Problem (measured)

`pacman.list_repository_updates()` runs **`pacman -Qu`**, which compares installed packages against
the **local sync db** (`/var/lib/pacman/sync`). That db is only as fresh as the last `pacman -Sy`
(terminal or an authenticated Atlas sync). Atlas's startup sync needs root and fails silently when
the user hasn't authenticated (see the sync-severity fix), so the sync db can be badly stale.

On a real machine right now: `pacman -Qu` → **3** updates; `checkupdates` → **~190**. AUR (live RPC)
and Flatpak (live remote) report correctly, so the user sees those updates but **silently misses
official-repo updates** — the worst failure mode for a package manager.

## Fix

Prefer **`checkupdates`** (pacman-contrib) for repo-update detection: it syncs a *temporary* db
without root (via fakeroot) and reports accurately regardless of the system db's freshness. Output
is identical to `pacman -Qu` (`name old -> new`); exit **2 = no updates** (success), **0 = updates**,
anything else = error.

- New pure `parse_repository_updates(output)` (extracted from the existing inline parse).
- `list_repository_updates()` tries `_checkupdates_updates()` first; **falls back to `pacman -Qu`**
  when checkupdates is absent (not installed), errors, or times out (e.g. offline). So it's a pure
  improvement — never worse than today, no regression when pacman-contrib isn't present.
- `pacman-contrib` added as an **optdepends** in the Arch PKGBUILD (optional — graceful fallback).

## Non-goals / deferred
- Not prompting for root on startup (bauh-style) — checkupdates removes the need; the lazy-auth model
  stays. (The opt-in "sync on startup" setting remains a possible future toggle, now lower value.)
- Not caching/rate-limiting checkupdates — it's delta-based (first run downloads dbs, later runs are
  tiny). Revisit only if startup latency is measured as a problem.

## Tests
- `parse_repository_updates`: normal lines, empty, junk-tolerant.
- `list_repository_updates`: checkupdates-present path (mock returns 0+output / 2+empty) and the
  fallback-to-`-Qu` path (checkupdates missing / non-0,2 exit).
