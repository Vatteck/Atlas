# Implementation: native pacman info parser + dormant-native fix

Companion to `2026-05-29-native-pacman-info-parser-design.md`.

> **Status: the native parser was REVERTED (2026-05-29).** It worked and was
> parity-tested but measured only ~1.2× (result-marshalling-bound), not worth two
> parsers — see the lesson below. **The two bug fixes found while doing it REMAIN in
> place**: the dormant-native import fix and the `map_missing_deps` disable. The clean
> `_parse_info_output_py` extraction (+ its test `test_pacman_info.py`) was also kept.

## What shipped

1. **`rust/src/pacman.rs`** — `parse_info_output` is now a free function;
   `PacmanPackage::to_deps_data(include_description)` gates `des` and emits `null` for
   empty `d`/`c` (matching Python `None`); parses Description/Download/Installed sizes.
2. **`rust/src/lib.rs`** — new `parse_pacman_info(output, description)` PyO3 function +
   a recursive `serde_json::Value → PyObject` converter (returns a real nested dict, no
   `json.loads` needed). Registered in the module.
3. **`atlas/gems/arch/pacman.py`** — extracted the parse loop into
   `_parse_info_output_py` (the fallback + benchmark reference); `map_updates_data`
   uses the native parser for the `pacman -Si` path (`files=False`) behind the
   `native.load()` gate, converting list fields back to sets for type parity.

## Two bugs surfaced and fixed along the way

- **CRITICAL — native was dormant in production.** `native.load()` (and the original
  `dependencies.py`) did a bare `import atlas_rs`, which does **not** resolve at runtime
  (the module is installed as `atlas.gems.arch.atlas_rs`). So every native path silently
  returned `None` and fell back to Python — the native resolver had never actually run
  outside the `sys.path`-hacked smoke script. Fixed: `native.load()` now imports
  `from atlas.gems.arch import atlas_rs`.
- **Native `map_missing_deps` is not a faithful drop-in.** Once the import was fixed, it
  went live and broke 5 `test_updates` tests: it re-derives the graph from real
  `pacman`/AUR calls and ignores the caller's pre-fetched inputs (`pkgs_data`,
  `provided_map`, `remote_*_map`, `aur_index`, `deps_data`), bypassing mocked data and
  changing behavior. **Disabled** its wiring in `dependencies.py` (the Rust resolver
  stays, unit-tested, for a future rework that accepts caller context).

## Verification

- `cargo test` → 14 passed.
- `tests/gems/arch/test_pacman_info_parity.py` (new): runs `map_updates_data` with native
  enabled vs `ATLAS_DISABLE_RS`, asserts identical output. Now actually executes the
  native path (was skipping due to the import bug).
- `python -m pytest tests/` → 176 passed (was 171 + 5 failed mid-change).
- `benchmarks/bench_pacman_info.py` (release): **~1.2× faster** than Python — modest,
  because returning ~100 structured dicts makes PyO3 result-marshalling + the list→set
  conversion dominate the parse win. (Contrast `map_srcinfo` ~2×, which returns one dict.)

## Lesson

Parsing ports only pay off when the *result* is small. When the operation returns a large
structured result, PyO3 marshalling erodes the gain. Weigh that before porting more
parsers that return per-package dicts.
