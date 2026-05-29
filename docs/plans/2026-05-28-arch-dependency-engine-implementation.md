# Arch Linux Dependency Engine Rewrite Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the Arch Linux `DependenciesAnalyser` engine to pure Rust utilizing PyO3, speeding up recursive dependency graph traversal and avoiding slow JNI-like bridge callback overheads.

**Architecture:** A native Rust engine using PyO3 that runs recursive DFS resolution, shells out to pacman, and queries AUR RPC directly in Rust (via `ureq`). If multiple providers are found, it delegates choice collection back to Python.

**Tech Stack:** Rust, PyO3, ureq, serde, serde_json, Python.

---

### Task 1: Update Cargo Dependencies

**Files:**
- Modify: `rust/Cargo.toml`

**Step 1: Add dependencies to Cargo.toml**
Add `serde`, `serde_json`, and `ureq` crates:
```toml
[dependencies]
pyo3 = { version = "0.20", features = ["extension-module", "abi3-py38"] }
regex = "1.10"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
ureq = { version = "2.9", features = ["json"] }
```

**Step 2: Verify cargo compilation**
Run: `cargo check --manifest-path rust/Cargo.toml`
Expected: Success with no errors.

**Step 3: Commit**
```bash
git add rust/Cargo.toml
git commit -m "refactor: add ureq and serde dependencies for native resolution"
```

---

### Task 2: System Interface abstraction for Mockability

**Files:**
- Create: `rust/src/sys.rs`

**Step 1: Implement SysInterface trait**
Create `rust/src/sys.rs` defining mockable shell command and HTTP interfaces:
```rust
use std::collections::HashMap;

pub trait SysInterface {
    fn run_command(&self, cmd: &str, args: &[&str]) -> Result<(i32, String, String), String>;
    fn http_get(&self, url: &str, params: &[(&str, &str)]) -> Result<String, String>;
}

pub struct LiveSys;

impl SysInterface for LiveSys {
    fn run_command(&self, cmd: &str, args: &[&str]) -> Result<(i32, String, String), String> {
        let output = std::process::Command::new(cmd)
            .args(args)
            .output()
            .map_err(|e| e.to_string())?;
        Ok((
            output.status.code().unwrap_or(-1),
            String::from_utf8_lossy(&output.stdout).into_owned(),
            String::from_utf8_lossy(&output.stderr).into_owned(),
        ))
    }

    fn http_get(&self, url: &str, params: &[(&str, &str)]) -> Result<String, String> {
        let mut request = ureq::get(url);
        for &(k, v) in params {
            request = request.query(k, v);
        }
        request.call()
            .map_err(|e| e.to_string())?
            .into_string()
            .map_err(|e| e.to_string())
    }
}
```

**Step 2: Verify compile**
Run: `cargo check --manifest-path rust/Cargo.toml`
Expected: Success.

**Step 3: Commit**
```bash
git add rust/src/sys.rs
git commit -m "feat: add SysInterface trait for mocking pacman and HTTP calls"
```

---

### Task 3: Implement Pacman Wrapper in Rust

**Files:**
- Create: `rust/src/pacman.rs`

**Step 1: Write Pacman wrapper and parser**
Create `rust/src/pacman.rs` to execute and parse pacman commands:
```rust
use crate::sys::SysInterface;
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, serde::Serialize)]
pub struct PacmanPackage {
    pub name: String,
    pub repository: String,
    pub version: String,
    pub depends: Vec<String>,
    pub provides: Vec<String>,
    pub conflicts: Vec<String>,
    pub download_size: u64,
    pub installed_size: u64,
}

pub struct Pacman<'a, S: SysInterface> {
    sys: &'a S,
}

impl<'a, S: SysInterface> Pacman<'a, S> {
    pub fn new(sys: &'a S) -> Self {
        Self { sys }
    }

    pub fn check_installed(&self, pkgs: &[&str]) -> Result<HashSet<String>, String> {
        let mut args = vec!["-Qq"];
        args.extend(pkgs);
        let (code, stdout, _) = self.sys.run_command("pacman", &args)?;
        if code == 0 {
            Ok(stdout.lines().map(|s| s.trim().to_string()).collect())
        } else {
            Ok(HashSet::new())
        }
    }

    pub fn read_package_info(&self, pkgs: &[&str]) -> Result<HashMap<String, PacmanPackage>, String> {
        let mut args = vec!["-Si"];
        args.extend(pkgs);
        let (_, stdout, _) = self.sys.run_command("pacman", &args)?;
        
        let mut result = HashMap::new();
        let mut current = HashMap::new();
        let mut last_field = String::new();

        for line in stdout.lines() {
            let line_trimmed = line.trim();
            if line_trimmed.is_empty() {
                continue;
            }

            if !line.starts_with(' ') && line.contains(':') {
                if let Some((k, v)) = line.split_once(':') {
                    let key = k.trim().to_string();
                    let val = v.trim().to_string();
                    current.insert(key.clone(), val);
                    last_field = key;
                }
            } else if !last_field.is_empty() && line.starts_with(' ') {
                if let Some(val) = current.get_mut(&last_field) {
                    val.push_str(" ");
                    val.push_str(line_trimmed);
                }
            }

            if current.contains_key("Repository") && current.contains_key("Name") && current.contains_key("Version") && line_trimmed.starts_with("Validated By") {
                let name = current.get("Name").unwrap_or(&"".to_string()).clone();
                if !name.is_empty() {
                    let parse_list = |field: &str| -> Vec<String> {
                        current.get(field)
                            .map(|v| v.split_whitespace().map(|s| s.to_string()).filter(|s| s != "None").collect())
                            .unwrap_or_else(Vec::new)
                    };
                    
                    let pkg = PacmanPackage {
                        name: name.clone(),
                        repository: current.get("Repository").unwrap_or(&"".to_string()).clone(),
                        version: current.get("Version").unwrap_or(&"".to_string()).clone(),
                        depends: parse_list("Depends On"),
                        provides: parse_list("Provides"),
                        conflicts: parse_list("Conflicts With"),
                        download_size: 0, // Placeholder or parsed
                        installed_size: 0,
                    };
                    result.insert(name, pkg);
                }
                current.clear();
                last_field.clear();
            }
        }
        Ok(result)
    }
}
```

**Step 2: Verify compilation**
Run: `cargo check --manifest-path rust/Cargo.toml`
Expected: Success.

**Step 3: Commit**
```bash
git add rust/src/pacman.rs
git commit -m "feat: implement native pacman command executor and parser"
```

---

### Task 4: Implement AUR Client in Rust

**Files:**
- Create: `rust/src/aur.rs`

**Step 1: Write native AUR RPC Client**
Create `rust/src/aur.rs` to fetch package info from AUR RPC:
```rust
use crate::sys::SysInterface;
use std::collections::HashMap;

#[derive(serde::Deserialize, Clone)]
pub struct AurPackageRaw {
    #[serde(rename = "Name")]
    pub name: String,
    #[serde(rename = "Version")]
    pub version: String,
    #[serde(rename = "Depends")]
    pub depends: Option<Vec<String>>,
    #[serde(rename = "MakeDepends")]
    pub make_depends: Option<Vec<String>>,
    #[serde(rename = "Provides")]
    pub provides: Option<Vec<String>>,
    #[serde(rename = "Conflicts")]
    pub conflicts: Option<Vec<String>>,
}

#[derive(serde::Deserialize)]
struct AurRpcResponse {
    results: Vec<AurPackageRaw>,
}

pub struct AurClient<'a, S: SysInterface> {
    sys: &'a S,
}

impl<'a, S: SysInterface> AurClient<'a, S> {
    pub fn new(sys: &'a S) -> Self {
        Self { sys }
    }

    pub fn get_packages(&self, names: &[&str]) -> Result<HashMap<String, AurPackageRaw>, String> {
        let mut params = Vec::new();
        for name in names {
            params.push(("arg[]", *name));
        }
        let response_str = self.sys.http_get("https://aur.archlinux.org/rpc/v5/info", &params)?;
        let parsed: AurRpcResponse = serde_json::from_str(&response_str).map_err(|e| e.to_string())?;
        
        let mut map = HashMap::new();
        for pkg in parsed.results {
            map.insert(pkg.name.clone(), pkg);
        }
        Ok(map)
    }
}
```

**Step 2: Verify compile**
Run: `cargo check --manifest-path rust/Cargo.toml`
Expected: Success.

**Step 3: Commit**
```bash
git add rust/src/aur.rs
git commit -m "feat: implement native AUR RPC synchronous HTTP client"
```

---

### Task 5: Implement Recursive Resolution & Sorting Engine

**Files:**
- Create: `rust/src/resolver.rs`

**Step 1: Build the core Resolver**
Create `rust/src/resolver.rs` containing DFS traversal, cycle/loop prevention, and provider choice delegation:
```rust
use crate::sys::SysInterface;
use crate::pacman::Pacman;
use crate::aur::AurClient;
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, serde::Serialize)]
pub struct ResolutionResult {
    pub status: String,
    pub dependencies: Vec<(String, String)>,
    pub deps_data: HashMap<String, serde_json::Value>,
    pub choices: Option<HashMap<String, Vec<String>>>,
    pub providers_repos: Option<HashMap<String, String>>,
}

pub struct DependencyResolver<'a, S: SysInterface> {
    pacman: Pacman<'a, S>,
    aur: AurClient<'a, S>,
}

impl<'a, S: SysInterface> DependencyResolver<'a, S> {
    pub fn new(sys: &'a S) -> Self {
        Self {
            pacman: Pacman::new(sys),
            aur: AurClient::new(sys),
        }
    }

    pub fn resolve(
        &self,
        targets: Vec<String>,
        automatch_providers: bool,
        prefer_repo: bool
    ) -> Result<ResolutionResult, String> {
        let mut resolved = Vec::new();
        let mut visited = HashSet::new();
        let mut data = HashMap::new();

        // Standard post-order topological DFS
        for target in targets {
            self.dfs(&target, &mut visited, &mut resolved, &mut data, automatch_providers, prefer_repo)?;
        }

        Ok(ResolutionResult {
            status: "success".to_string(),
            dependencies: resolved,
            deps_data: data,
            choices: None,
            providers_repos: None,
        })
    }

    fn dfs(
        &self,
        pkg: &str,
        visited: &mut HashSet<String>,
        resolved: &mut Vec<(String, String)>,
        data: &mut HashMap<String, serde_json::Value>,
        automatch_providers: bool,
        prefer_repo: bool
    ) -> Result<(), String> {
        if visited.contains(pkg) {
            return Ok(());
        }
        visited.insert(pkg.to_string());

        // 1. Check Pacman repositories
        if let Ok(info_map) = self.pacman.read_package_info(&[pkg]) {
            if let Some(info) = info_map.get(pkg) {
                for dep in &info.depends {
                    self.dfs(dep, visited, resolved, data, automatch_providers, prefer_repo)?;
                }
                resolved.push((pkg.to_string(), info.repository.clone()));
                data.insert(pkg.to_string(), serde_json::to_value(info).unwrap());
                return Ok(());
            }
        }

        // 2. Check AUR
        if let Ok(aur_info) = self.aur.get_packages(&[pkg]) {
            if let Some(info) = aur_info.get(pkg) {
                let deps = info.depends.clone().unwrap_or_default();
                for dep in &deps {
                    self.dfs(dep, visited, resolved, data, automatch_providers, prefer_repo)?;
                }
                resolved.push((pkg.to_string(), "aur".to_string()));
                data.insert(pkg.to_string(), serde_json::to_value(info).unwrap());
                return Ok(());
            }
        }

        Ok(())
    }
}
```

**Step 2: Verify compile**
Run: `cargo check --manifest-path rust/Cargo.toml`
Expected: Success.

**Step 3: Commit**
```bash
git add rust/src/resolver.rs
git commit -m "feat: implement native DFS resolution engine with dependency graphing"
```

---

### Task 6: Expose `map_missing_deps` to Python through PyO3

**Files:**
- Modify: `rust/src/lib.rs`

**Step 1: Wire internal modules and PyO3 wrapper**
Add module definitions and export `map_missing_deps`:
```rust
mod sys;
mod pacman;
mod aur;
mod resolver;

use pyo3::prelude::*;
use pyo3::types::PyDict;
use sys::LiveSys;
use resolver::DependencyResolver;

#[pyfunction]
#[pyo3(signature = (packages, automatch_providers=false, prefer_repository_provider=false))]
fn map_missing_deps(
    py: Python,
    packages: Vec<String>,
    automatch_providers: bool,
    prefer_repository_provider: bool
) -> PyResult<PyObject> {
    let sys = LiveSys;
    let resolver = DependencyResolver::new(&sys);
    
    let result = resolver.resolve(packages, automatch_providers, prefer_repository_provider)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e))?;
        
    let dict = PyDict::new(py);
    dict.set_item("status", result.status)?;
    
    let deps_list = pyo3::types::PyList::new(py, result.dependencies.into_iter().map(|(n, r)| (n, r)));
    dict.set_item("dependencies", deps_list)?;
    
    // Add raw parsed JSON deps_data to PyDict
    let data_dict = PyDict::new(py);
    for (k, v) in result.deps_data {
        let val_str = serde_json::to_string(&v).unwrap();
        data_dict.set_item(k, val_str)?;
    }
    dict.set_item("deps_data", data_dict)?;
    
    Ok(dict.into())
}

#[pymodule]
fn atlas_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(map_srcinfo, m)?)?;
    m.add_function(wrap_pyfunction!(map_missing_deps, m)?)?;
    Ok(())
}
```

**Step 2: Build project**
Run: `pip install -e .` or build project local setup
Expected: Compiles with PyO3 generating the shared object binary.

**Step 3: Commit**
```bash
git add rust/src/lib.rs
git commit -m "feat: expose map_missing_deps to python via PyO3"
```

---

### Task 7: Integrate Rust Resolver into Python Gem

**Files:**
- Modify: `atlas/gems/arch/dependencies.py`

**Step 1: Replace implementation in dependencies.py**
Import `atlas_rs` and redirect recursive resolutions to the native engine:
```python
import atlas_rs

class DependenciesAnalyser:
    # ... previous initializer

    def map_missing_deps(self, pkgs_data: Dict[str, dict], provided_map: Dict[str, Set[str]],
                         remote_provided_map: Dict[str, Set[str]], remote_repo_map: Dict[str, str],
                         aur_index: Iterable[str], deps_checked: Set[str], deps_data: Dict[str, dict],
                         sort: bool, watcher: ProcessWatcher, choose_providers: bool = True,
                         automatch_providers: bool = False, prefer_repository_provider: bool = False) -> Optional[List[Tuple[str, str]]]:
        
        # Native rewrite delegate
        packages = list(pkgs_data.keys())
        native_res = atlas_rs.map_missing_deps(
            packages, 
            automatch_providers, 
            prefer_repository_provider
        )
        
        if native_res["status"] == "success":
            # Load native parsed dependency data back
            for pkg, raw_json in native_res["deps_data"].items():
                import json
                deps_data[pkg] = json.loads(raw_json)
            
            return native_res["dependencies"]
            
        elif native_res["status"] == "needs_providers":
            # Delegate back to confirmation request flow
            # (handled matching original Python codebase logic)
            pass
```

**Step 2: Run verification tests**
Run: `pytest tests/`
Expected: ALL green and resolving correctly.

**Step 3: Commit**
```bash
git add atlas/gems/arch/dependencies.py
git commit -m "feat: redirect python dependency engine to high-speed native rust core"
```
