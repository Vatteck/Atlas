use crate::sys::SysInterface;
use crate::pacman::Pacman;
use crate::aur::AurClient;

use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
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

    pub fn split_dep(dep: &str) -> (String, Option<String>, Option<String>) {
        let operators = [">=", "<=", "==", ">", "<", "="];
        for op in &operators {
            if let Some(idx) = dep.find(op) {
                let name = dep[..idx].trim().to_string();
                let operator = op.to_string();
                let version = dep[idx + op.len()..].trim().to_string();
                return (name, Some(operator), Some(version));
            }
        }
        (dep.trim().to_string(), None, None)
    }

    pub fn resolve(
        &self,
        targets: Vec<String>,
        automatch_providers: bool,
        prefer_repo: bool,
    ) -> Result<ResolutionResult, String> {
        let mut resolved = Vec::new();
        let mut visited = HashSet::new();
        let mut data = HashMap::new();
        let mut path = Vec::new();

        for target in targets {
            let (name, _, _) = Self::split_dep(&target);
            self.dfs(&name, &mut visited, &mut path, &mut resolved, &mut data, automatch_providers, prefer_repo)?;
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
        path: &mut Vec<String>,
        resolved: &mut Vec<(String, String)>,
        data: &mut HashMap<String, serde_json::Value>,
        automatch_providers: bool,
        prefer_repo: bool,
    ) -> Result<(), String> {
        if path.contains(&pkg.to_string()) {
            // Cycle detected - skip or warning, but don't panic
            return Ok(());
        }
        if visited.contains(pkg) {
            return Ok(());
        }

        path.push(pkg.to_string());

        // 1. Check if package is installed already
        let installed = self.pacman.check_installed(&[pkg])?;
        if installed.contains(pkg) {
            path.pop();
            visited.insert(pkg.to_string());
            return Ok(());
        }

        // 2. Query pacman repositories
        if let Ok(info_map) = self.pacman.read_package_info(&[pkg]) {
            if let Some(info) = info_map.get(pkg) {
                for dep in &info.depends {
                    let (dep_name, _, _) = Self::split_dep(dep);
                    self.dfs(&dep_name, visited, path, resolved, data, automatch_providers, prefer_repo)?;
                }
                resolved.push((pkg.to_string(), info.repository.clone()));
                data.insert(pkg.to_string(), info.to_deps_data());
                path.pop();
                visited.insert(pkg.to_string());
                return Ok(());
            }
        }

        // 3. Query AUR
        if let Ok(aur_info) = self.aur.get_packages(&[pkg]) {
            if let Some(info) = aur_info.get(pkg) {
                let deps = info.depends.clone().unwrap_or_default();
                for dep in &deps {
                    let (dep_name, _, _) = Self::split_dep(dep);
                    self.dfs(&dep_name, visited, path, resolved, data, automatch_providers, prefer_repo)?;
                }
                resolved.push((pkg.to_string(), "aur".to_string()));
                data.insert(pkg.to_string(), info.to_deps_data());
                path.pop();
                visited.insert(pkg.to_string());
                return Ok(());
            }
        }

        path.pop();
        visited.insert(pkg.to_string());
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sys::MockSys;

    #[test]
    fn test_split_dep() {
        assert_eq!(
            DependencyResolver::<MockSys>::split_dep("yakuake>=24.0.0"),
            ("yakuake".to_string(), Some(">=".to_string()), Some("24.0.0".to_string()))
        );
        assert_eq!(
            DependencyResolver::<MockSys>::split_dep("bash"),
            ("bash".to_string(), None, None)
        );
    }

    #[test]
    fn test_resolver_success() {
        let sys = MockSys::new();
        
        // Mock pacman check_installed for yakuake and konsole (they are missing, i.e., not installed)
        sys.commands.borrow_mut().insert(
            "pacman -Qq yakuake".to_string(),
            Ok((1, "".to_string(), "error: package 'yakuake' was not found\n".to_string()))
        );
        sys.commands.borrow_mut().insert(
            "pacman -Qq konsole".to_string(),
            Ok((1, "".to_string(), "error: package 'konsole' was not found\n".to_string()))
        );
        
        // Mock pacman -Si for yakuake and konsole
        let mock_yakuake_si = r#"Repository      : extra
Name            : yakuake
Version         : 24.02.2-1
Depends On      : konsole
Validated By    : SHA-256 Sum
"#;
        let mock_konsole_si = r#"Repository      : extra
Name            : konsole
Version         : 24.02.2-1
Depends On      : None
Validated By    : SHA-256 Sum
"#;

        sys.commands.borrow_mut().insert(
            "pacman -Si yakuake".to_string(),
            Ok((0, mock_yakuake_si.to_string(), "".to_string()))
        );
        sys.commands.borrow_mut().insert(
            "pacman -Si konsole".to_string(),
            Ok((0, mock_konsole_si.to_string(), "".to_string()))
        );

        let resolver = DependencyResolver::new(&sys);
        let res = resolver.resolve(vec!["yakuake".to_string()], false, false).unwrap();

        assert_eq!(res.status, "success");
        // Topological order: konsole should be first, then yakuake!
        assert_eq!(
            res.dependencies,
            vec![
                ("konsole".to_string(), "extra".to_string()),
                ("yakuake".to_string(), "extra".to_string())
            ]
        );

        // deps_data must use the canonical short-key schema
        let yakuake_data = &res.deps_data["yakuake"];
        assert_eq!(yakuake_data["r"], "extra");
        assert_eq!(yakuake_data["v"], "24.02.2-1");
        assert!(yakuake_data["d"].as_array().unwrap()
            .iter().any(|v| v == "konsole"));
    }

    /// Helper: register a not-installed `pacman -Qq` result for a package.
    fn mock_not_installed(sys: &MockSys, pkg: &str) {
        sys.commands.borrow_mut().insert(
            format!("pacman -Qq {}", pkg),
            Ok((1, String::new(), format!("error: package '{}' was not found\n", pkg))),
        );
    }

    /// Helper: register a repo `pacman -Si` result with the given deps.
    fn mock_repo_pkg(sys: &MockSys, pkg: &str, depends: &str) {
        let si = format!(
            "Repository      : extra\nName            : {}\nVersion         : 1.0-1\nDepends On      : {}\nValidated By    : SHA-256 Sum\n",
            pkg, depends
        );
        sys.commands.borrow_mut().insert(format!("pacman -Si {}", pkg), Ok((0, si, String::new())));
    }

    #[test]
    fn test_resolver_target_already_installed() {
        let sys = MockSys::new();
        sys.commands.borrow_mut().insert(
            "pacman -Qq vim".to_string(),
            Ok((0, "vim\n".to_string(), String::new())),
        );

        let resolver = DependencyResolver::new(&sys);
        let res = resolver.resolve(vec!["vim".to_string()], false, false).unwrap();

        assert_eq!(res.status, "success");
        assert!(res.dependencies.is_empty());
        assert!(res.deps_data.is_empty());
    }

    #[test]
    fn test_resolver_aur_fallback() {
        let sys = MockSys::new();
        mock_not_installed(&sys, "yay");
        // not in any repo -> empty -Si output forces the AUR path
        sys.commands.borrow_mut().insert(
            "pacman -Si yay".to_string(),
            Ok((0, String::new(), String::new())),
        );
        sys.http.borrow_mut().insert(
            "https://aur.archlinux.org/rpc/v5/info?arg[]=yay".to_string(),
            Ok(r#"{"results":[{"Name":"yay","Version":"12.0-1"}]}"#.to_string()),
        );

        let resolver = DependencyResolver::new(&sys);
        let res = resolver.resolve(vec!["yay".to_string()], false, false).unwrap();

        assert_eq!(res.dependencies, vec![("yay".to_string(), "aur".to_string())]);
        assert_eq!(res.deps_data["yay"]["r"], "aur");
    }

    #[test]
    fn test_resolver_cycle_terminates() {
        let sys = MockSys::new();
        mock_not_installed(&sys, "a");
        mock_not_installed(&sys, "b");
        mock_repo_pkg(&sys, "a", "b");
        mock_repo_pkg(&sys, "b", "a");

        let resolver = DependencyResolver::new(&sys);
        let res = resolver.resolve(vec!["a".to_string()], false, false).unwrap();

        // Both resolved exactly once despite the a <-> b cycle.
        assert_eq!(res.dependencies.len(), 2);
        let names: Vec<&str> = res.dependencies.iter().map(|(n, _)| n.as_str()).collect();
        assert!(names.contains(&"a") && names.contains(&"b"));
    }

    #[test]
    fn test_resolver_diamond_shared_dep_once() {
        let sys = MockSys::new();
        for p in ["top", "left", "right", "base"] {
            mock_not_installed(&sys, p);
        }
        mock_repo_pkg(&sys, "top", "left right");
        mock_repo_pkg(&sys, "left", "base");
        mock_repo_pkg(&sys, "right", "base");
        mock_repo_pkg(&sys, "base", "None");

        let resolver = DependencyResolver::new(&sys);
        let res = resolver.resolve(vec!["top".to_string()], false, false).unwrap();

        let names: Vec<&str> = res.dependencies.iter().map(|(n, _)| n.as_str()).collect();
        assert_eq!(names.iter().filter(|&&n| n == "base").count(), 1, "base must appear once");
        // base must come before both consumers, and top must be last (post-order)
        let pos = |n: &str| names.iter().position(|&x| x == n).unwrap();
        assert!(pos("base") < pos("left") && pos("base") < pos("right"));
        assert_eq!(names.last(), Some(&"top"));
    }

    #[test]
    fn test_split_dep_all_operators() {
        let cases = [
            ("pkg>=1.0", ("pkg", Some(">="), Some("1.0"))),
            ("pkg<=1.0", ("pkg", Some("<="), Some("1.0"))),
            ("pkg==1.0", ("pkg", Some("=="), Some("1.0"))),
            ("pkg>1.0", ("pkg", Some(">"), Some("1.0"))),
            ("pkg<1.0", ("pkg", Some("<"), Some("1.0"))),
            ("pkg=1.0", ("pkg", Some("="), Some("1.0"))),
        ];
        for (input, (name, op, ver)) in cases {
            assert_eq!(
                DependencyResolver::<MockSys>::split_dep(input),
                (name.to_string(), op.map(String::from), ver.map(String::from)),
                "input: {}", input
            );
        }
    }
}
