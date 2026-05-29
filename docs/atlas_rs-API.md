# `atlas_rs` — Native Module API Reference

`atlas_rs` is the Rust/PyO3 extension that backs Atlas's one CPU-bound hot path. It is
built from `rust/` and installed as **`atlas.gems.arch.atlas_rs`** (see `setup.py`). For
the design rationale and boundary rules, read [ARCHITECTURE.md §3](./ARCHITECTURE.md).

> **Status:** deliberately minimal. After measuring (see [ROADMAP.md](./ROADMAP.md) and
> [STATUS.md](./STATUS.md)), the only native function that earns its keep is
> `map_srcinfo` (~2× on a small, CPU-bound result). The earlier native dependency
> resolver and pacman-info parser were removed — they were I/O-bound or
> marshalling-bound, so the PyO3 boundary erased the benefit.

---

## Importing

Always import via the qualified path, and through the `srcinfo` wrapper which adds the
Python fallback:

```python
from atlas.gems.arch.srcinfo import map_srcinfo   # native-first, Python fallback
```

A bare `import atlas_rs` does **not** resolve at runtime (the module installs as
`atlas.gems.arch.atlas_rs`). `atlas/gems/arch/native.py` centralizes loading
(`native.load()`) and honours `ATLAS_DISABLE_RS` / `ATLAS_RS_DEBUG`.

---

## `map_srcinfo(string, pkgname=None, fields=None)`

Parses pacman/`.SRCINFO`-style `key = value` text into a dict, handling repeated keys
(list fields) and multi-package (`pkgbase`/`pkgname`) blocks in a single pass.

### Parameters
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `string` | `str` | — | The raw `key = value` text to parse. |
| `pkgname` | `Optional[str]` | `None` | When the text has multiple `pkgname` blocks, restrict the merge to this package. Ignored when only one package is present. |
| `fields` | `Optional[Set[str]]` | `None` | If given, only these keys are collected. `None` = collect everything. |

### Returns
`Dict[str, Union[str, List[str]]]` — scalar fields as `str`; known list fields (and any
key appearing more than once) as a `list`. List values are de-duplicated, so **order is
not preserved** for list fields. List-field keys are in `KNOWN_LIST_FIELDS` in
`rust/src/lib.rs` (`depends*`, `makedepends*`, `provides`, `conflicts`, `source*`, etc.).

### Fallback
`atlas/gems/arch/srcinfo.py` wraps this: it tries native via `native.load()` and falls
back to `_map_srcinfo_py` (the original pure-Python parser) if the module is unavailable
or `ATLAS_DISABLE_RS` is set. Native and Python outputs are parity-tested
(`tests/gems/arch/test_srcinfo.py`), including `fields` cases.

---

## History (removed native paths)

Kept here so the next agent doesn't re-attempt them without reading why:

- **`map_missing_deps` / dependency resolver** (`resolver.rs`, `aur.rs`, `pacman.rs`,
  `sys.rs`) — removed 2026-05-29. The Python `DependenciesAnalyser.map_missing_deps` is
  dominated by live pacman/AUR I/O, recursion, and watcher-driven provider choices (UI),
  not CPU. A faithful native drop-in would require Rust→Python callbacks and would not be
  faster. The prototype also ignored the caller's pre-fetched data and re-fetched it.
- **`parse_pacman_info`** — removed 2026-05-29. A native `pacman -Si` parser measured
  only ~1.2× because it returns many per-package dicts; PyO3 result-marshalling plus the
  list→set conversion dominated. Parser ports only pay off for *small* results.

The lesson (also in STATUS.md and benchmarks/README.md): **only port CPU-bound
operations that return small results.**

---

## Adding a new exposed function

1. Implement it in `rust/src/lib.rs` as a `#[pyfunction]` and register it in the
   `#[pymodule]` block.
2. On the Python side, call it behind a fallback via `native.load()` (see `srcinfo.py`
   as the template).
3. Benchmark it on a **release** build (`benchmarks/`) and only keep it if it's a
   meaningful, measured win on a small result.
4. Document the signature here.
