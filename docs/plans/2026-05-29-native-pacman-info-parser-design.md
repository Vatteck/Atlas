# Design: wire the native pacman info parser into `map_updates_data`

## Goal

Route `pacman.py:map_updates_data` parsing through the existing Rust `pacman.rs` parser
(behind a Python fallback), reusing code we already wrote and shipping a measurable
parsing speedup. Phase 2 category ("native pacman parsing"); a parsing-port like
`map_srcinfo`, which measured ~2× on release builds.

## Boundary

Expose a **pure** function:

```python
atlas_rs.parse_pacman_info(output: str, description: bool = False) -> Dict[str, dict]
```

Python keeps its `run_cmd` (root handling, logging, the `-Si` vs `-Qi -p` choice) and
hands the captured stdout to Rust for parsing. This is the right coarse boundary for a
parser: one big string in, one dict out; no subprocess logic to re-port; trivially
unit-, differential-, and benchmark-testable as a pure function.

`map_updates_data(pkgs, files=False)` uses the native path; `files=True` (`pacman -Qi -p`
on local package files) stays on Python for now (different output shape — no Repository /
Download Size — verify separately before routing it through Rust).

## Output schema parity (authoritative: `pacman.py:map_updates_data`)

Per package: `{r, v, d, p, c, s, ds, des}`.

| key | Python | Rust emits | parity step |
|-----|--------|-----------|-------------|
| `r` | Repository string | repository string | — (always present for `-Si`) |
| `v` | `Version` split on `=` | same | — |
| `d` | `None` if "None" else **set** | `null` if empty else list | Python wiring: list→set |
| `p` | **set**: name, name=version, provides, base names | list, same contents | Python wiring: list→set |
| `c` | `None` if "None" else **set** | `null` if empty else list | Python wiring: list→set |
| `s` | `size_to_byte(Installed Size)` float | same (size_to_byte port) | — |
| `ds`| `size_to_byte(Download Size)` float | same | — |
| `des`| `Description` only if `description=True` else `None` | controlled by flag | — |

The Python consumers never mutate `p/d/c` (verified), so converting the native lists to
sets in the wiring yields identical types to the pure-Python path.

## Rust changes

- `pacman.rs`: make `parse_info_output` a free function (no `&self`); have
  `PacmanPackage::to_deps_data(include_description: bool)` gate `des`, and emit `null`
  for empty `d` (matching Python's `None`; `c` already does this).
- `resolver.rs`: update the two call sites to `to_deps_data(true)`.
- `lib.rs`: add `parse_pacman_info` + a `serde_json::Value → PyObject` converter so the
  result is a real nested dict (no `json.loads` needed by the caller).

## Verification

- Rust unit tests for `parse_pacman_info` (multi-package, None handling, description flag).
- `benchmarks/bench_pacman_info.py`: A/B the Python parse loop vs `parse_pacman_info` on
  representative `-Si` output, asserting equivalent output first (release build).
- `python -m pytest tests/gems/arch/`.
