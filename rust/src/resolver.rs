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
                data.insert(pkg.to_string(), serde_json::to_value(info).unwrap());
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
                data.insert(pkg.to_string(), serde_json::to_value(info).unwrap());
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
    }
}
