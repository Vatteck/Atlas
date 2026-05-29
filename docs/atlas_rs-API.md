# `atlas_rs` — Native Module API Reference

`atlas_rs` is the Rust/PyO3 extension that backs Atlas's hot paths. It is built from
`rust/` and installed as **`atlas.gems.arch.atlas_rs`** (see `setup.py`). For the
design rationale and the boundary rules, read [ARCHITECTURE.md §3](./ARCHITECTURE.md).

> **Status:** early. Two functions are exposed today. Every function has a Python
> fallback on the consuming side, so callers must tolerate the module being absent or a
> call raising.

---

## Importing

```python
try:
    import atlas_rs
except ImportError:
    atlas_rs = None     # fall back to the pure-Python path
```

The module is also importable as `from atlas.gems.arch import atlas_rs` depending on how
it was built/installed; the bare `import atlas_rs` is what the current call sites use.

---

## `map_srcinfo(string, pkgname=None, fields=None)`

Parses pacman/`.SRCINFO`-style `key = value` text into a dict, handling repeated keys
(list fields) and multi-package (`pkgbase`/`pkgname`) blocks in a single pass.

### Parameters
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `string` | `str` | — | The raw `key = value` text to parse. |
| `pkgname` | `Optional[str]` | `None` | When the text contains multiple `pkgname` blocks, restrict the merge to this package. Ignored when only one package is present. |
| `fields` | `Optional[Set[str]]` | `None` | If given, only these keys are collected. `None` = collect everything. |

### Returns
`Dict[str, Union[str, List[str]]]` — scalar fields come back as `str`; known list
fields (and any key that appears more than once) come back as a `list`.

Keys treated as list fields regardless of count include:
`depends*`, `makedepends*`, `checkdepends*`, `optdepends*`, `provides`, `conflicts`,
`source*`, `sha256sums*`, `sha512sums*`, `validpgpkeys` (and their `_x86_64` / `_i686`
arch variants). See `KNOWN_LIST_FIELDS` in `rust/src/lib.rs`.

### Notes
- List values are de-duplicated (backed by a `HashSet`), so **order is not preserved**
  for list fields. Don't rely on ordering of e.g. `depends`.

---

## `map_missing_deps(packages, automatch_providers=False, prefer_repository_provider=False)`

Resolves the full set of missing dependencies for the given packages: shells out to
pacman, queries the AUR RPC, walks the dependency graph (recursive DFS with cycle
detection), and returns them in topological install order — all inside Rust, in one
call.

### Parameters
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `packages` | `List[str]` | — | Target package names to resolve dependencies for. |
| `automatch_providers` | `bool` | `False` | Auto-select a provider when its name matches the required (virtual) package exactly. |
| `prefer_repository_provider` | `bool` | `False` | When choosing among providers, prefer official-repo packages over AUR. |

### Returns — success
```python
{
  "status": "success",
  "dependencies": [            # topologically sorted install order
    ["dep1", "extra"],         # (package_name, repository)
    ["dep2", "aur"],
  ],
  "deps_data": {
    "dep1": "<json string>",   # ⚠ JSON-encoded string, not a nested dict
  },
}
```

`deps_data` values are **JSON strings** and must be decoded by the caller
(`json.loads(...)`). Each decodes to a per-package record:

| Key | Meaning |
|-----|---------|
| `ds` | download size (bytes) |
| `s` | installed size (bytes) |
| `v` | version (e.g. `"1.0-1"`) |
| `c` | conflicts (or `null`) |
| `p` | provides (list) |
| `d` | depends (list) |
| `r` | repository |
| `des` | description |

### Returns — provider choice needed *(designed, not yet wired)*
The internal `ResolutionResult` struct (`rust/src/resolver.rs`) carries a
`needs_providers` shape:
```python
{
  "status": "needs_providers",
  "choices": { "virtual_pkg": ["pkg_a", "pkg_b"] },
  "providers_repos": { "pkg_a": "extra", "pkg_b": "aur" },
}
```
⚠️ **Gap:** `map_missing_deps` in `rust/src/lib.rs` currently only serializes
`status`, `dependencies`, and `deps_data` into the returned dict — it does **not** yet
copy `choices` / `providers_repos` out. Until that's added, the native path can't
surface provider choices to Python, so the consuming code must treat any non-`"success"`
status as "fall back to Python." Wiring these fields through is a tracked follow-up.

### Caller contract
The consumer (`atlas/gems/arch/dependencies.py:404`) uses the native result **only** on
`status == "success"`, decodes `deps_data` via `json.loads`, returns
`native_res["dependencies"]`, and otherwise falls through to the pure-Python resolver.
On **any** exception it silently falls back. See ARCHITECTURE §3.2 for why the fallback
exists and the plan to make swallowed errors visible (`ATLAS_RS_DEBUG`).

---

## Internal modules (not exposed to Python)

These back the public functions and are where new native logic is added:

| Module | Responsibility |
|--------|----------------|
| `sys.rs` | `SysInterface` trait (`run_command`, `http_get`) + `LiveSys`; the seam mocked in tests. |
| `pacman.rs` | Native parsing of `pacman -Si` / `-Qi` (multiline records). |
| `aur.rs` | Synchronous AUR RPC client (`ureq` + `serde_json`), batched `GET` to `/rpc/v5/info`. |
| `resolver.rs` | `DependencyResolver`: DFS traversal, cycle detection, provider matching, topological sort; returns `ResolutionResult`. |

All system access goes through `SysInterface`, so resolver/parsing logic is unit-tested
without a live system or network. Add new I/O by extending the trait, not by calling
`std::process` / `ureq` from logic code.

---

## Adding a new exposed function

1. Implement the logic in a module under `rust/src/`, taking `&impl SysInterface`.
2. Add a `#[pyfunction]` wrapper in `lib.rs` that builds a `LiveSys`, calls the logic,
   and converts the result to Python types (return a `dict` with a `status`
   discriminator for anything structured).
3. Register it in the `#[pymodule] fn atlas_rs(...)` block via `wrap_pyfunction!`.
4. On the Python side, call it behind the existing implementation as a fallback.
5. Document the signature and payload schema in this file.

See [DEVELOPMENT.md §6](./DEVELOPMENT.md) for the full workflow and
[ROADMAP.md](./ROADMAP.md) for what to add next (hot paths first).
