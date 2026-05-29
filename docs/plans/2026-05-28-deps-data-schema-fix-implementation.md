# Implementation: Fix native `deps_data` schema mismatch

Companion to `2026-05-28-deps-data-schema-fix-design.md`. Status: **done**.

## Tasks

1. **`rust/src/pacman.rs`** ✅
   - Added `description: Option<String>`, changed `download_size`/`installed_size` to
     `Option<f64>`, and parsed `Description` / `Download Size` / `Installed Size`
     (previously dropped).
   - Added module fn `size_to_byte(num, unit)` mirroring `atlas.commons.util.size_to_byte`.
   - Added `PacmanPackage::to_deps_data()` emitting the canonical short-key schema with
     the provides `name` / `name=version` / base-name semantics.

2. **`rust/src/aur.rs`** ✅
   - Added `AurPackageRaw::to_deps_data()` (`r="aur"`, sizes/description null).

3. **`rust/src/resolver.rs`** ✅
   - `dfs` now stores `info.to_deps_data()` instead of `serde_json::to_value(info)` in
     both the repo and AUR branches.

4. **Tests** ✅ — `cargo test`: 13 passing (was 4). Added:
   - `pacman`: `test_size_to_byte`, `test_to_deps_data_schema`, description/size parsing
     in `test_parse_info_output`.
   - `aur`: `test_aur_to_deps_data_schema`, `test_aur_get_packages_empty_input`.
   - `resolver`: `test_resolver_target_already_installed`, `test_resolver_aur_fallback`,
     `test_resolver_cycle_terminates`, `test_resolver_diamond_shared_dep_once`,
     `test_split_dep_all_operators`, plus a schema assertion in `test_resolver_success`.

## Verification

- `cargo test --manifest-path rust/Cargo.toml` → 13 passed.
- Rebuilt the extension (`CARGO_INCREMENTAL=0 pip install -e .`).
- End-to-end via the native module on a real package (`tree`):
  `deps_data` keys = `['c','d','des','ds','p','r','s','v']`; `s=96256.0`, `ds=44564.48`
  (parsed to bytes), `des` populated, `c=None`, `p=['tree','tree=2.3.2-1', ...]`.
- `python -m pytest tests/gems/arch/` → 73 passed.

## Build note

`pip install -e .` can fail with `package directory 'rust/target/debug/incremental/...'
does not exist` when Cargo incremental artifacts churn during setuptools' file walk
(e.g. right after `cargo test`). Workaround: `CARGO_INCREMENTAL=0` and/or
`rm -rf rust/target/debug/incremental` before building.

## Still open (separate tasks)

- Provider auto-matching and the `needs_providers` return path remain unimplemented.
- AUR `d` uses the RPC `Depends` field directly rather than replicating
  `extract_required_dependencies` (acceptable approximation).
