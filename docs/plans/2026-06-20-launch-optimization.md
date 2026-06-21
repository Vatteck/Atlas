# Launch-time optimization — 2026-06-20

Follow-up to the launch-time baseline (STATUS Done, 2026-06-20). Goal: reduce time-to-window
before the stable `atlas-pm` publish. Decision was **A then evaluate B** (see below).

## Baseline (system Python 3.14.5, warm cache, best-of-N)

| Layer | Cost | Notes |
|---|---:|---|
| Backend (interpreter → pre-window, main thread) | ~572 ms | imports + config + `load_managers` + `import webview` |
| GTK/WebKit window construction (`webview.start` → `shown`) | ~555 ms | native, unavoidable |
| WebKit parse of the front-end bundle (`shown` → `loaded`) | ~1040 ms | **464 KB**: main.js 324 KB + style.css 112 KB + index.html 28 KB |
| **time-to-window** | **~1127 ms** | |
| **time-to-DOM** | **~2170 ms** | first-view *data* (attention-center) renders async after this |

## Avenue A — lazy-import the HTTP/parse stack (DONE)

**What:** the `requests` stack (`requests`→`urllib3`→`charset_normalizer`→`chardet`) and the web
gem's `bs4`+`lxml` were imported at module top in several files. `load_managers` imports **every**
gem controller (enabled or not), so these landed on the launch critical path even though no network
call / page-parse happens until well after the window is shown.

**Changed** (move `import requests` into the methods that use it; build lazily where subclassed):
- `atlas/app.py` — dropped top-level `import urllib3`; the `disable_warnings` call moved into
  `HttpClient.session` (first use).
- `atlas/api/http.py` — `from __future__ import annotations`; lazy `requests`; session built lazily.
- `atlas/commons/category.py`, `atlas/gems/appimage/worker.py`, `atlas/gems/arch/aur.py`,
  `atlas/gems/arch/worker.py`, `atlas/gems/web/environment.py`, `atlas/gems/web/suggestions.py` —
  lazy `requests` inside the network methods.
- `atlas/gems/snap/snapd.py` — the urllib3/requests adapter subclasses are built lazily in
  `_build_snapd_adapter()` (they used to subclass at module scope).
- `atlas/gems/web/controller.py` — `from __future__ import annotations`; `bs4`/`lxml` detected via
  `importlib.util.find_spec` (no heavy import) in `_bs4_available()`/`_lxml_available()`;
  `BeautifulSoup` imported lazily in `_map_url`; lazy `requests`.

**Verified:** after `load_managers()`, none of requests/urllib3/charset_normalizer/chardet/bs4/lxml
are in `sys.modules`. Suite **707** still green.

**Measured outcome:** verified clean (none of the stacks in `sys.modules` after `load_managers`).
A standalone before/after for A is **not separable** from B with confidence — an early A/B was
confounded (the throwaway `/tmp` harness ran with `sys.path[0]=/tmp`, so it imported the **installed
0.13.0 snapshot**, not the working tree; a `git stash` A/B on the working tree therefore compared
old-vs-old and showed ~0 difference — a *measurement artifact*, not A's real effect). A is kept
because it is clean, behaviour-preserving, low-maintenance, and ensures the HTTP/parse stack is built
**off the main thread** under B (so it doesn't compete with the window-first critical path), and it
helps cold start. The combined A+B win is measured below.

> **Measurement gotcha (learned here):** benchmark scripts must import the **working tree**, not the
> installed package. Run them with `PYTHONPATH=<repo>` (or from the repo with `python -c`), and
> clear `__pycache__` after edits. The installed `atlas` at
> `/usr/lib/python3.14/site-packages/atlas` is a non-editable snapshot.

## Avenue B — show the window before backend init (DONE)

The real time-to-window lever. `app.main()` used to build context + `load_managers` + manager +
`AtlasApi` **before** `webview.create_window`. Now (strangler-fig, **default on**, fallback via
`ATLAS_LEGACY_STARTUP=1`):

- `atlas/app.py` — factored the backend build into `build_manager()`. Default path constructs
  `AtlasApi(manager=None)`, creates + shows the window, then builds the manager on a daemon thread
  (`atlas-backend-build`) and calls `api.set_manager(mgr)` + starts the tray from that thread. GTK
  window construction (mostly native / GIL-releasing) runs concurrently with gem probing.
- `atlas/view/webview/api.py` — `manager` is now a **blocking property** backed by a
  `threading.Event`; `set_manager()` attaches it and kicks off `_prepare_manager`. Every existing
  `self.manager` access transparently waits, so no call site changed. `is_backend_ready()` is a
  non-blocking probe for the splash. Legacy `AtlasApi(manager, logger)` still works (tests + fallback).
- **Boot splash** (`index.html` `#boot-splash`, `style.css` `.boot-splash*`, `main.js`
  `waitForBackendReady`/`hideBootSplash`): shown over everything; `pywebviewready` polls
  `is_backend_ready()` then fades the splash and runs the first fetch. Because the WebKit parse
  (~1 s) outlasts the backend build (~440 ms), the splash mostly covers the parse window — the user
  sees a branded splash from ~800 ms instead of a blank window, then content.

**Measured (best-of-5, working tree vs installed 0.13.0 baseline, same machine):**
time-to-window **1152 ms → 805 ms (~347 ms, ~30% faster)**. Backend becomes ready ~440 ms (warm),
concurrently with window construction. Suite **707** + JS contracts green; real `app.py` boots clean.
**Splash visuals need a GUI eyeball.**

## Avenue C — trim the WebKit parse (NOT pursued)

Biggest single layer (~1040 ms) but minifying/splitting the 464 KB bundle adds a **build step**,
conflicting with the solo-dev low-maintenance goal. Revisit only if B proves insufficient.

## Status

- A: **done**, kept (lazy HTTP/parse stack; off-main-thread under B).
- B: **done** — window-first + splash; **~347 ms / 30%** faster time-to-window; `ATLAS_LEGACY_STARTUP=1`
  fallback. Needs a GUI eyeball on the splash.
- C: parked (build-step maintenance cost).
