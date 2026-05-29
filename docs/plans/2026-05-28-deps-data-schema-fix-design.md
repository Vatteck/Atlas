# Design: Fix native `deps_data` schema mismatch

## Problem

The native `atlas_rs.map_missing_deps` "success" path returns `deps_data[pkg]` dicts
keyed by the Rust struct field names (`name`, `repository`, `depends`, ... and for AUR
the capitalized `Name`, `Depends`, ...). The Python consumers expect the project's
canonical **short-key** schema (`d`, `p`, `r`, `v`, `s`, `ds`, `c`, `des`). Downstream
reads (`data['d']`, `info['p']`, ...) happen *outside* the `try/except` in
`dependencies.py`, so on a genuine native success this is a hard `KeyError`, not a caught
fallback. It has been masked because the native path almost always falls back before
returning success. Surfaced by Phase 0 instrumentation.

## Canonical schema (authoritative source: `pacman.py:get_information` + `aur.py:map_update_data`)

Per package, `deps_data[pkg]`:

| Key | Meaning | Type | Notes |
|-----|---------|------|-------|
| `r` | repository | string | `"aur"` for AUR packages |
| `v` | version | string | repo: `Version` split on `=`; aur: RPC version |
| `d` | depends | array | deduped; empty array when none |
| `p` | provides | array | **always includes `name` and `name=version`**, plus each `Provides` entry and the base name of any versioned (`foo=1.0` → also `foo`) |
| `c` | conflicts | array \| null | `null` when none |
| `s` | installed size | number \| null | bytes via `size_to_byte`; `null` for AUR |
| `ds` | download size | number \| null | bytes via `size_to_byte`; `null` for AUR |
| `des` | description | string \| null | `null` for AUR |

`size_to_byte(num, unit)`: `b`→num/8, `B`→num; else base = 1024 if unit ends with `ib`
else 1000, multiplied by base^1..^5 for k/m/g/t/(other) by the unit's first letter.

`b` (pkgbase) is intentionally omitted — no consumer reads it from `deps_data`.

## Approach

Give `PacmanPackage` and `AurPackageRaw` a `to_deps_data(&self) -> serde_json::Value`
method that emits the canonical schema, and have `resolver::dfs` store
`info.to_deps_data()` instead of `serde_json::to_value(info)`. This keeps each source
module responsible for its own mapping and leaves the resolver/graph logic untouched.

`pacman.rs` must additionally parse `Description`, `Download Size`, and `Installed Size`
(currently dropped), and compute the provides set with the `name` / `name=version`
semantics.

Provides/depends/conflicts cross as JSON **arrays** (Python builds them as sets, but the
consumers only iterate / membership-test, both of which work on a list; values are
deduped in Rust to mirror set semantics).

## Out of scope

Provider auto-matching and the `needs_providers` return path remain unimplemented
(separate tracked gap). AUR `d` uses the RPC `Depends` field directly rather than
replicating `extract_required_dependencies`; acceptable approximation, noted in STATUS.
