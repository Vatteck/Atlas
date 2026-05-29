# Design: Arch Linux Dependency Engine Rust Rewrite

We are migrating the recursive dependency graph resolution engine for Arch Linux from Python (`atlas/gems/arch/dependencies.py`) to a native Rust implementation inside `atlas_rs` using PyO3.

## 1. High-Level Architecture & PyO3 API

To avoid slow cross-boundary callbacks, Python delegates the entire resolution task to a single high-level Rust function:

```python
def map_missing_deps(
    packages: List[str], 
    automatch_providers: bool = False,
    prefer_repository_provider: bool = False
) -> Dict[str, Any]:
```

### Return Payload Schema

#### Success State:
```json
{
  "status": "success",
  "dependencies": [
    ["dep1", "extra"],
    ["dep2", "aur"]
  ],
  "deps_data": {
    "dep1": {
      "ds": 1024,
      "s": 2048,
      "v": "1.0-1",
      "c": null,
      "p": ["dep1"],
      "d": ["dep2"],
      "r": "extra",
      "des": "Example package"
    }
  }
}
```

#### Provider Choice State:
```json
{
  "status": "needs_providers",
  "choices": {
    "virtual_pkg": ["pkg_a", "pkg_b"]
  },
  "providers_repos": {
    "pkg_a": "extra",
    "pkg_b": "aur"
  }
}
```

---

## 2. Internal Rust Components

### Pacman Shell Interface
- Executes commands via `std::process::Command` directly in Rust.
- Parses output of `pacman -Si <pkgs>` and `pacman -Qi <pkgs>` using a highly optimized, single-pass zero-copy/string parser.
- Spawns `pacman -Qq` to quickly verify package installation states.

### Synchronous AUR RPC Client
- Uses `ureq` + `serde_json` to fetch package data in batches.
- Bypasses Python's async or multithreading overhead completely.
- Formats requests as standard `GET` requests to `https://aur.archlinux.org/rpc/v5/info`.

---

## 3. Resolution & Sorting Algorithm

1. **State Tracking**: Uses a `ResolverState` struct containing hash sets for visited packages, mapping data, and topological paths.
2. **Recursive Traversal**: Implements standard DFS graph traversal with cycle/loop detection.
3. **Provider Auto-matching**:
   - Compares providers to target names (if exact match, auto-selects).
   - If `prefer_repository_provider` is true, official repository packages are chosen over AUR packages.
4. **Topological Sort**: Employs post-order DFS sorting to guarantee dependent installation orders.

---

## 4. Resilient Error Handling & Testing

- Swaps live calls for mocked `SysInterface` traits in tests.
- Gracefully intercepts network timeouts and parses invalid/missing package states.
- Exposes tests directly in `rust/src/` for unit-level verification.
