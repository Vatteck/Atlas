# Startup memory baseline — 2026-07-17

Motivated by user reports of high RAM usage at startup. Golden rule 6: measure before
optimizing. All numbers from this dev box (CachyOS, Python 3.14, 2177 installed pkgs,
warm caches), harnesses left ephemeral in the session scratchpad.

## Method

- Backend-only: phase-marked script replicating `build_manager()` from `app.py` +
  the first `read_installed` (the heavy call the GUI triggers). RSS from
  `/proc/self/status` (VmRSS/VmHWM), allocations via tracemalloc.
- Full app: launched the real GUI (`python -m atlas.app`, system Python — the venv has
  no pywebview) and sampled **PSS** for the whole process tree over 45 s
  (`/proc/<pid>/smaps_rollup`). PSS, not RSS: WebKit is multi-process and RSS
  double-counts shared pages — a task manager summing RSS will overstate real use.
- Floor: a minimal pywebview window with `<body>hi</body>`, same env workarounds.

## Results

Full app at startup, steady state (t=10–45 s): **~400–460 MB PSS total**
- python UI process: **218–234 MB**
- WebKitWebProcess (renderer): **148–150 MB**
- WebKitNetworkProcess: **33 MB**
- bwrap/glycin helpers: ~5 MB

Decomposition of the python UI process (~220 MB):
- **132 MB** = the *floor*: an empty pywebview/GTK window's UI process, before any
  Atlas code. GTK + WebKit embedding + JSC mapped into the process. Add the empty
  window's own web/network processes and **~200 MB PSS is the price of the
  pywebview/WebKitGTK architecture** for any app.
- Backend logic: 30 MB after full init (imports + config + i18n + load_managers +
  GenericSoftwareManager); **+46 MB** after the first `read_installed`
  (2177 pkgs, 5–7 s) → 76–79 MB, transient peak 95–98 MB. Python-heap live data is
  only ~22 MB — the rest is native/glibc retention.
- Remainder (~25–40 MB): API layer — `_serialize_pkg` registry (LRU 2000), bridge JSON
  strings, watcher/refresh threads.

Repeated `read_installed` (5×): 77 → 83 → 90 → 91 → 93 MB. Slow, **decelerating**
creep (~+2 MB/iter by the end) — reads as caches filling (AUR mapper, memory caches),
not an unbounded leak. Worth re-checking in a long-lived GUI session.

## Measured dead ends (do not re-try without new evidence)

- **tracemalloc inflates RSS ~3×** on this workload (190–220 MB vs 76–79 real). Never
  quote RSS from a tracemalloc run.
- **MALLOC_ARENA_MAX=2 made it worse**: 93.5 MB vs 79.1 baseline.
- **malloc_trim(0)**: reclaimed ~1 MB. Not worth wiring in.

## Candidate levers (none implemented — pending direction)

1. **Get the actual reports.** 400–460 MB PSS is Electron-class but not runaway; a
   task manager summing RSS shows ~600+ MB and *looks* worse. If reporters see
   multi-GB or growth-over-time, that's a different bug (bigger installs?
   Flatpak-heavy? no compositing workaround?) — need their numbers/setup.
2. **Renderer (~150 MB):** WebKitGTK cache model (`DOCUMENT_VIEWER` vs default
   browser-style caching) could trim renderer memory, but pywebview doesn't expose
   it — reaching into its GTK internals is a maintenance cost (solo-dev flag).
3. **Ship less across the bridge:** `get_installed` serializes all ~2.2k packages as
   one JSON payload (python registry + JS heap + DOM when the grid renders. The
   Installed view renders every card at once — virtualization would cap DOM but adds
   real complexity).
4. **Accept the floor:** ~200 MB is WebKitGTK itself; not addressable within the
   no-Qt/no-Rust guardrails.
