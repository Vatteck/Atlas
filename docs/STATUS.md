# STATUS — the handoff baton

> **This is the single most important file for cross-agent continuity.** It is the live
> state of the project. Read it at the start of every session; update it at the end of
> every session that changes code (see AGENTS.md §8). Keep it short and current — when an
> item is stale, fix it or delete it.

**Last updated:** 2026-06-01
**Version:** 0.10.7
**Working branch:** `master` (use short-lived branches for larger features; run `git branch` to see what's active)

---

## Current focus

**Webview privileged-operation flow — verified working (2026-06-01).** The Rust migration
is parked at its sensible end (only `map_srcinfo`). The pywebview privileged-op flow is now
confirmed end-to-end in the GUI: an Arch install (gimp) prompts for the root password,
renders the optdep checklist and the named missing-deps list, installs the selected optdeps,
and reports success. See [plans/2026-05-30-root-password-flow-design.md](plans/2026-05-30-root-password-flow-design.md).

## Next (per ROADMAP, hot paths first)

**Both planned tracks are essentially complete.** The Rust migration reached its sensible
end (only `map_srcinfo` earns its keep). And the Python-side startup wins (option 2) turn
out to be **already implemented + unit-tested** (verified 2026-05-29):
- `GenericSoftwareManager.prepare()` is lazy (only the config step is eager);
  per-manager lazy prep via `_ensure_prepared`/`_can_work` (per-manager locks).
- `AtlasApi` runs prepare off the UI thread via a shared `ThreadPoolExecutor(max_workers=5)`.
- Covered by `tests/view/webview/test_lazy_load.py`.

Remaining, optional & low-value: route the controller's ad-hoc `Thread(...)` spawns
(search / read-installed / suggestions) through a shared pool. Marginal benefit, real
risk — only do it with a measured reason. **Recommended instead:** manually launch
`atlas` to confirm real startup behavior and capture a launch-time baseline (no automated
GUI test exists).

The Rust migration verdict (after measuring everything): the PyO3 boundary only pays off
for **CPU-bound ops with small results**. `map_srcinfo` qualifies (~2×). The dependency
resolver (I/O+UI-bound) and the pacman info parser (marshalling-bound) did not and were
removed. Don't re-attempt them without reading the decision log.

See [ROADMAP.md](ROADMAP.md) for the full phased plan.

---

## Done

- **Flathub API v1 → v2 migration (2026-06-01):** Flathub retired the v1 REST API
  (`/api/v1/apps/{id}` → **404**), so Flatpak suggestion enrichment, the info panel and
  screenshots all failed (log spam: `Could not retrieve app data … Server response: ?`).
  Migrated to the v2 AppStream API behind a new `atlas/gems/flatpak/flathub.py` (the only
  module that knows the v2 endpoints/shape). Mapping highlights: `icon` is now an absolute
  URL; `categories` is a list of strings (was `[{name}]`); version/notes/date live under
  `releases[0]`; screenshots are `sizes[].src` (pick widest). Three callers updated
  (`worker.py`, `controller.get_info`, `controller.get_screenshots`). Pure mappers are
  unit-tested against a captured payload (`tests/gems/flatpak/test_flathub.py` +
  `resources/flathub_v2_appstream_gimp.json`). Plan:
  [plans/2026-06-01-flathub-v2-api-migration.md](plans/2026-06-01-flathub-v2-api-migration.md).
- **Confirm modal now renders input components (2026-06-01):** installing e.g. `gimp`
  showed the optdep prompt and the missing-deps prompt but **no list** — the modal only
  rendered title/body text. The confirm modal now renders checkbox lists, single-select
  radios/combos and forms, and round-trips the selections back into the gem's component
  objects (watcher `_serialize_components`/`_apply_selections`, JS `renderConfirmComponents`
  + `submit_confirmation(confirmed, selections)`). Fixes optdep selection, missing-deps
  display, and AUR provider choice. Tests: `tests/view/webview/test_watcher.py`.
- **Arch install reported "failed" though the package installed (2026-06-01):** installing
  e.g. `gimp` ran pacman successfully but the op reported **failed**. Two independent bugs,
  both fixed:
  1. **Root cause (the crash):** `pacman.map_update_sizes`/`map_download_sizes`/
     `get_installed_size` paired regex size-matches to the requested package names
     *positionally* (`pkgs[idx]` over `enumerate(RE.findall(output))`). `pacman -Si <names>`
     prints one block **per matching package**, so a package present in >1 enabled repo
     (e.g. `extra` + `extra-testing`) yields more size lines than names → `IndexError`
     (gimp's 7 repo optdeps produced 12 size lines). Fixed by parsing per-package blocks and
     mapping each block's `Name` → size (`_map_pkg_sizes`). Tests in `test_pacman.py`.
  2. **Defense in depth:** `_install_from_repository`/`_install_from_aur` returned the
     *optdep* step's result as the whole-install result, so any optdep failure/cancellation
     flipped an already-successful main install to "failed". Optdeps are optional — both
     paths now run them in a `try/except` and always return the main package's result
     (matching the code's own `# because the main package installation was successful`).
     Tests in `test_install_optdeps.py`.
- **All watcher dialogs are now HTML modals (2026-05-30):** converted
  `request_confirmation`/`request_reboot`/`show_message` off the dead
  `window.confirm`/`alert` to blocking HTML modals (`#confirm-modal`, `#message-modal` +
  `showConfirmModal`/`showMessageModal` in `main.js`), mirroring the password modal.
  AtlasApi gained `prompt_confirmation`/`prompt_message` + `submit_confirmation`/
  `submit_message_ack` callbacks; the watcher delegates and strips HTML from gem text via
  `_clean()`. Caveat: rich `components` aren't rendered (text only). 4 new tests.
- **Root-password flow for the webview (2026-05-30):** `api.py` passed
  `root_password=None` to every privileged op → Arch/AUR installs ran unprivileged and
  failed. Added a session-scoped broker on `AtlasApi` (`acquire_root_password` /
  `ensure_root_password` / `submit_root_password`) + an HTML password modal
  (`#password-modal` in `index.html`, `showPasswordModal` in `main.js`) replacing the
  broken `window.prompt` path, plus `validate_root_password()` in `commons/system.py`
  (`sudo -k -S -v`). Wired into install/uninstall/update/update_all/batch_uninstall/
  import; `WebviewWatcher` now delegates `request_root_password` to the broker. 3 new
  tests in `test_api.py`. **Needs GUI verification (can't be driven headless).**
- Rebrand bauh → Atlas (namespaces, config paths `~/.config/atlaspm` etc., UI strings).
- Qt5 UI purged; pywebview front-end (`atlas/view/webview/`) in place.
- `atlas_rs` build pipeline (PyO3 + setuptools-rust, `debug=False`), installed at
  `atlas.gems.arch.atlas_rs`. Crate is now `lib.rs` only; deps trimmed to just `pyo3`
  (`.so` ~621 KB, down from 3.6 MB).
- `map_srcinfo` — native `.SRCINFO`/pacman field parser (~2×), with a Python fallback
  in `srcinfo.py`. **The only surviving native function.**
- **Native dependency resolver removed** (`resolver.rs`/`aur.rs`/`pacman.rs`/`sys.rs` +
  `map_missing_deps`): I/O+UI-bound, not a useful Rust target (2026-05-29).
- Documentation set: ARCHITECTURE, ROADMAP, DEVELOPMENT, atlas_rs-API; cross-agent
  onboarding (AGENTS.md / CLAUDE.md / GEMINI.md) + this baton.
- **Phase 0 complete:** boundary instrumentation (`native.py` switches), `deps_data`
  schema fix, benchmark harness (`benchmarks/bench_srcinfo.py`), and the release-build
  fix (`setup.py debug=False`).
- **Native import fix (critical):** `native.load()` imported bare `atlas_rs`, which never
  resolves at runtime → the native path was dormant in production. Now imports
  `from atlas.gems.arch import atlas_rs`.
- **Native pacman info parser: tried then reverted.** Wired into `map_updates_data` and
  parity-tested, but only ~1.2× (marshalling-bound), so reverted to cut maintenance.
  Kept the clean `_parse_info_output_py` extraction (+ its correctness test). Lesson
  recorded in `benchmarks/README.md` and the roadmap.
- **map_srcinfo fallback restored** (`atlas/gems/arch/srcinfo.py`): native-first via
  `native.load()` with the original pure-Python parser as fallback; `aur.py` now imports
  from there. Closes the last native path with no fallback. Parity-tested (incl. `fields`).
- **Native resolver retired** (2026-05-29): removed the 4 dead Rust modules +
  `map_missing_deps` and trimmed Cargo deps. `map_srcinfo` still passes; full suite green.
- Full Python suite 183 — all green. (cargo test: 0 — `map_srcinfo` is covered by the
  Python parity test `test_srcinfo.py`.)

---

## Known gaps / gotchas (don't get burned)

- **WebKitGTK has no `window.prompt`/`confirm`/`alert`.** They return `null`/no-op, so the
  watcher's old `evaluate_js("window.prompt/confirm/alert(...)")` never worked. **All four
  are now HTML modals** (password, confirm, message) that block the worker thread on a
  `threading.Event` and resolve via `js_api` callbacks (`submit_root_password`,
  `submit_confirmation`, `submit_message_ack`). Never reintroduce a `window.*` dialog.
- **`request_confirmation` renders input components (2026-06-01).** The confirm modal now
  renders `MultipleSelectComponent` (checkbox list), `SingleSelectComponent` (radio or
  combo), `FormComponent`, and `TextComponent`, and returns the user's selections. The
  watcher serializes the component tree (`_serialize_components`) and applies the returned
  option-index selections back onto the original objects (`_apply_selections`) so arch's
  `request_optional_deps` / `confirm_missing_deps` / `request_providers` read the choices
  as before. Covered by `tests/view/webview/test_watcher.py`. Not yet rendered: option
  icons (decorative; repo/aur svgs are skipped) and component types outside the four above
  (none are used in confirmation flows today).
- **Root password requires the GUI to drive it; can't verify headless.** The broker shows
  a modal and blocks a pywebview worker thread on a `threading.Event`. Relies on pywebview
  dispatching each `js_api` call on its own thread (true for the GTK backend). User must
  confirm install/cancel/wrong-password behaviour in the running GUI.

- **Tray mode is gone (was broken).** The rebrand purged Qt but left `tray.py`/`manage.py`
  importing the deleted `atlas.view.qt.*` — `atlas-tray` crashed on launch. Removed them +
  the `atlas-tray` entry point + `--tray` arg + `context.new_qt_application`/`set_theme`
  (2026-05-29). README roadmap notes a non-Qt tray could be reintroduced.
- **Residual PyQt5 coupling remains** (not yet cleaned): `view/core/settings.py`
  (`qt_style` property), `view/util/util.py` (`QCoreApplication.exit()`),
  `stylesheet.py`, and `app.py`'s optional HDPI block, plus `pyqt5` in pyproject deps.
  The webview GUI still pulls in PyQt5 through these. Decide later whether to fully
  de-Qt or keep PyQt5 as an optional dep. Verify each is actually reachable before
  removing.
- **App run-status:** ✅ GUI confirmed working (user launched `python -m atlas.app` on
  2026-05-29 — window loads, lazy gem init fires, background prepare ~10ms, suggestions
  run). Remaining log noise is expected: first-run (no cache/db), no-root (`pacman -Sy`
  can't sync), harmless pywebview GTK `window.native.*` warnings, and `atlas-files`
  download failures.
- ~~**`atlas-files` repo content.**~~ Resolved: `github.com/Vatteck/atlas-files` exists
  (cloned from `bauh-files`) and **all 10 download paths return 200** (verified
  2026-05-29, both `master` and `main` serve content). Content is package-manager-
  agnostic with no `bauh`/`vinifmor` self-references, so it works for Atlas as-is. The
  earlier launch-log download failures were just timing (predated the repo).
  *Optional later:* curate Atlas-specific suggestions/categories instead of bauh's
  defaults, and refresh the (possibly dated) electron/nativefier versions in
  `web/env/v2/environment.yml`.

- ~~**Silent fallback hides Rust bugs.**~~ Addressed: native calls now go through
  `atlas/gems/arch/native.py`; run with `ATLAS_RS_DEBUG=1` to log native failures, or
  `ATLAS_DISABLE_RS=1` to force the Python path. (Default behaviour still falls back
  silently.)
- ~~**`map_srcinfo` had no Python fallback.**~~ Fixed: `atlas/gems/arch/srcinfo.py`
  wraps native with the original Python parser; a missing `.so` no longer breaks the
  Arch gem at import. (Native and Python verified to agree, including `fields` cases.)
- **Don't re-attempt a native dependency resolver.** Removed 2026-05-29. The Python
  `map_missing_deps` is I/O-bound (pacman/AUR), recursive, and UI-coupled (watcher
  provider choices) — not CPU. A native port needs Rust→Python callbacks and isn't
  faster. The prototype also re-derived everything, ignoring caller context.
- **Lesson — only port CPU-bound ops with small results.** The native pacman info parser
  measured only ~1.2× (PyO3 result-marshalling + list→set conversion dominate when
  returning many dicts) and was reverted; the resolver was I/O-bound. `map_srcinfo`
  (~2×, one compact dict) is the shape that works. Weigh CPU-vs-I/O and result size
  before any new native path.
- **Rebuild reminder:** editing `rust/src/*` requires `pip install -e .` to take effect.
  If that fails with a `rust/target/debug/incremental/... does not exist` error, build
  with `CARGO_INCREMENTAL=0` (Cargo's incremental dirs churn during setuptools' walk).
- ~~**Debug builds are slower than Python.**~~ Fixed via `setup.py debug=False` (installs
  are now release). The benchmark proved a debug `atlas_rs` runs ~4× *slower* than the
  Python it replaced; release runs ~2× faster. **Always benchmark a release build.**
- Large Python files to read in sections, not whole: `controller.py` (~192 KB),
  `updates.py` (~42 KB), `pacman.py` (~38 KB).

---

## Decision log (append-only; newest first)

- **2026-05-30** — Converted the remaining `window.confirm`/`alert` watcher dialogs
  (`request_confirmation`/`request_reboot`/`show_message`) to blocking HTML modals, reusing
  the password-broker pattern (evaluate_js → worker blocks on Event → `js_api` callback
  resolves). Rich `components` are intentionally not rendered yet (text only). Same root
  cause as the password fix: WebKitGTK has no native JS dialogs.
- **2026-05-30** — Fixed Arch/AUR "no root access" installs. Root cause: `api.py`
  hardcoded `root_password=None` and the only prompt path used `window.prompt` (dead in
  WebKitGTK). Added a session-cached root-password broker on `AtlasApi` + HTML modal +
  `validate_root_password` (`sudo -k -S -v`), wired into all privileged ops, and pointed
  `WebviewWatcher.request_root_password` at the broker. Design:
  `plans/2026-05-30-root-password-flow-design.md`. Awaiting GUI verification.
- **2026-05-29** — GUI confirmed working end-to-end. Fixed 6 rebrand-leftover URLs still
  pointing at `vinifmor/...` (→ `Vatteck/...`): appimage dbs, arch categories + gpg
  servers, appimage app repo, setup.py + pyproject repository URL.
- **2026-05-29** — Ran the app for the first time; found `atlas-tray` broken (dead Qt
  imports the rebrand purge missed). Removed the broken tray + orphaned `manage.py` +
  `new_qt_application`/`set_theme` + the `atlas-tray` entry point and `--tray` arg.
  `context.py` no longer needs PyQt5. README/STATUS updated; tray reintro is roadmapped.
- **2026-05-29** — Retired the native dependency resolver: removed `resolver.rs`,
  `aur.rs`, `pacman.rs`, `sys.rs`, the `map_missing_deps` PyO3 fn, and the `serde`/
  `serde_json`/`ureq`/`regex` deps. Reason: I/O+UI-bound, not a viable Rust target (a
  faithful drop-in needs Rust→Python callbacks for pacman/AUR/watcher and wouldn't be
  faster). `lib.rs` is now `map_srcinfo` only; `.so` 3.6 MB → 621 KB. Migration verdict:
  port only CPU-bound ops with small results. Pivoting to Python-side startup wins.
- **2026-05-29** — Reverted the native pacman info parser (~1.2×, marshalling-bound) to
  cut maintenance surface; kept the `_parse_info_output_py` extraction + test. Confirms
  the rule: only port parsers with small results.
- **2026-05-29** — Restored a Python fallback for `map_srcinfo` (`srcinfo.py`); it was the
  only native function with none, so a missing `.so` would have broken the Arch gem.
  Native↔Python parity verified (incl. `fields`).
- **2026-05-29** — Wired native pacman `-Si` parser into `map_updates_data` (parity-tested,
  ~1.2×). Fixed the critical dormant-native import bug (bare `import atlas_rs` never
  resolved). Disabled the non-faithful native `map_missing_deps`. Chose the pacman-parser
  task after finding version-compare is NOT the update hot path (pacman -Qu does repo
  comparison; per-call vercmp across PyO3 would be slower than Python).
- **2026-05-28** — Phase 0 closed with a benchmark (`benchmarks/bench_srcinfo.py`). It
  revealed `pip install -e .` shipped a *debug* `atlas_rs` (~4× slower than Python);
  pinned `setup.py debug=False` → release builds, native now ~2× faster. Lesson encoded:
  always measure release builds.
- **2026-05-28** — Fixed native `deps_data` schema: Rust emits canonical short keys via
  per-source `to_deps_data()`; pacman.rs parses Description/Download/Installed sizes.
  Rust tests 4→13; verified end-to-end on a real package. Plans under `docs/plans/`.
- **2026-05-28** — Phase 0 instrumentation: all native (`atlas_rs`) calls route through
  `atlas/gems/arch/native.py` with `ATLAS_RS_DEBUG` / `ATLAS_DISABLE_RS` switches.
  Default still falls back silently; switches add visibility + an escape hatch.
- **2026-05-28** — Adopted AGENTS.md as the single canonical agent manual; CLAUDE.md and
  GEMINI.md are thin redirects to avoid drift across Claude/Codex/Gemini.
- **2026-05-28** — Migration strategy fixed as **strangler-fig, hot paths first**: Rust
  added behind Python fallbacks, fallback removed only after the native path is proven.
- **2026-05-28** — Python↔Rust boundary is **coarse-grained**: one whole task per call,
  no Rust→Python callbacks (rationale in ARCHITECTURE §3).

---

## Template for a STATUS update (copy when editing)

```
**Last updated:** YYYY-MM-DD
- Moved <item> from Next → Done.
- New Current focus: <…>. New Next: <…>.
- New gotcha discovered: <…> (and where it lives).
- Decision: <what + why>.
```
