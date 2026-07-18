# Coalesce concurrent read_installed passes — 2026-07-17

Follow-up to [2026-07-17-memory-baseline.md](2026-07-17-memory-baseline.md). After the
`pacman -Ql` streaming fix, the remaining cold-start transient (~200 MB of python peak
over steady state) comes from up to three **full `read_installed` passes running
concurrently** at startup: the GUI's updates read (`get_updates`), its installed read
(`get_installed`), and the first-run pre-cacher's own read. Each pass spawns per-gem
threads, pacman/checkupdates subprocesses, and AUR RPC parsing — concurrency stacks
their transient allocations (and burns 5–30 s of duplicate work on every warm start
too, e.g. the cold-run log shows two GUI reads finishing within 1 s of each other).

## Design: in-flight request coalescing (leader/follower)

In `GenericSoftwareManager.read_installed`:

- All eight `api.py` call sites invoke it with **no arguments** — identical full reads.
  (`disk_loader` is discarded by the method body; `limit`/`only_apps`/
  `internet_available` are unused; only `pkg_types` changes behavior.)
- When `pkg_types` is falsy (a full read): take a lock; if no full read is in flight,
  become the **leader** and run the real read; otherwise **follow** — wait on the
  leader's `threading.Event` and return its `SearchResult`.
- The in-flight slot is cleared before the event is set, so a call arriving *after* a
  read completes always triggers a fresh read — this is **concurrent dedup only, no
  result cache, no TTL**. The staleness window equals the duration of one read, a race
  that already existed between overlapping reads.
- A leader exception is stored and re-raised in followers (their own read could equally
  have failed).
- Typed reads (`pkg_types` set) bypass entirely — different results, rare callers.
- Followers share the leader's `SearchResult` object. Callers already treat it
  read-only (they build filtered lists; the shared pkg instances are already shared
  app-wide via the serialization registry).
- The pre-cacher's read (`ArchDiskCacheUpdater` → ArchManager-level, `names=` filter,
  `wait_disk_cache=False`) is **not** touched — different layer, different args, runs
  once ever.

Strangler-fig kill-switch: `ATLAS_NO_READ_COALESCING=1` restores fully independent
reads.

## Changes

- `controller.py`: `__init__` gains `_full_read_lock`/`_full_read_flight`; the old
  `read_installed` body becomes `_read_installed_now`; `read_installed` is the
  coalescing wrapper (same signature).
- Tests (`tests/view/core/test_read_coalescing.py`): concurrent calls → inner read runs
  once, both callers get the same result; sequential calls → two reads; `pkg_types`
  bypasses; leader exception propagates to followers; kill-switch env restores
  independent reads.

## Measured outcome (same day) — honest tally

Implemented, 5 tests green. **No measured memory delta on this box:**

- Cold fresh-HOME peak: 454.4 / 452.6 MB across runs vs 451.7 before — noise-level.
- Warm peak: 432.5 MB with coalescing vs 432.2 with the kill-switch on — identical.

Why: the GUI-triggered overlap is **timing-dependent**. In the original cold-run log the
two GUI reads overlapped by ~4 s (that motivated this work), but in post-change bench
runs they arrived sequentially (second started 4–20 s after the first finished), so
there was nothing to merge — and sequential reads *must not* be merged (fresh data).
The coalescing is kept as a cheap (~30-line, kill-switched) guard for the overlap class
that does occur — slow cold reads + multiple frontend surfaces triggering at once
(refresh button + badge + attention center).

**The real cold-start pair is structural, out of scope here:** the GUI's ArchManager
read *waits* for the pre-cacher's disk-cache task (`_wait_for_disk_cache`), while the
pre-cacher runs its own uncached read *as the data source* for that cache — so cold
start inherently runs two arch passes with the GUI one blocked on the worker. Merging
them means the ArchManager read path reusing the pre-cacher's in-flight result (or vice
versa) — an arch-gem redesign with deadlock potential (the cache-wait is circular),
needing its own plan. Until measured otherwise, the cold peak (~452 MB python VmHWM,
down from 529 pre-streaming-fix) stands.
