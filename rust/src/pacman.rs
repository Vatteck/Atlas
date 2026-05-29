use crate::sys::SysInterface;
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
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
        if pkgs.is_empty() {
            return Ok(HashSet::new());
        }
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
        if pkgs.is_empty() {
            return Ok(HashMap::new());
        }
        let mut args = vec!["-Si"];
        args.extend(pkgs);
        let (_, stdout, _) = self.sys.run_command("pacman", &args)?;
        Ok(self.parse_info_output(&stdout))
    }

    pub fn parse_info_output(&self, output: &str) -> HashMap<String, PacmanPackage> {
        let mut result = HashMap::new();
        let mut current_fields: HashMap<String, String> = HashMap::new();
        let mut last_field = String::new();

        let commit_package = |fields: &mut HashMap<String, String>, res: &mut HashMap<String, PacmanPackage>| {
            if let Some(name) = fields.get("Name").map(|s| s.trim().to_string()) {
                if !name.is_empty() {
                    let parse_list = |f_name: &str| -> Vec<String> {
                        fields.get(f_name)
                            .map(|val| {
                                val.split_whitespace()
                                    .map(|s| s.trim().to_string())
                                    .filter(|s| !s.is_empty() && s.to_lowercase() != "none")
                                    .collect()
                            })
                            .unwrap_or_else(Vec::new)
                    };

                    let pkg = PacmanPackage {
                        name: name.clone(),
                        repository: fields.get("Repository").cloned().unwrap_or_default(),
                        version: fields.get("Version").cloned().unwrap_or_default(),
                        depends: parse_list("Depends On"),
                        provides: parse_list("Provides"),
                        conflicts: parse_list("Conflicts With"),
                        download_size: 0,
                        installed_size: 0,
                    };
                    res.insert(name, pkg);
                }
            }
            fields.clear();
        };

        for line in output.lines() {
            let line_trimmed = line.trim_end();
            if line_trimmed.trim_start().is_empty() {
                continue;
            }

            if !line.starts_with(' ') && line.contains(':') {
                if let Some((k, v)) = line.split_once(':') {
                    let key = k.trim().to_string();
                    let val = v.trim().to_string();

                    // If we see Name or Repository and we already have a package name populated, we transition
                    if (key == "Name" || key == "Repository") && current_fields.contains_key("Name") {
                        commit_package(&mut current_fields, &mut result);
                    }

                    current_fields.insert(key.clone(), val);
                    last_field = key;
                }
            } else if !last_field.is_empty() && line.starts_with(' ') {
                if let Some(val) = current_fields.get_mut(&last_field) {
                    val.push(' ');
                    val.push_str(line_trimmed.trim_start());
                }
            }
        }

        commit_package(&mut current_fields, &mut result);
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sys::MockSys;

    #[test]
    fn test_parse_info_output() {
        let raw_si = r#"Repository      : extra
Name            : yakuake
Version         : 24.02.2-1
Provides        : None
Depends On      : konsole  kwayland
                  kxmlgui
Conflicts With  : None
Validated By    : SHA-256 Sum

Repository      : extra
Name            : konsole
Version         : 24.02.2-1
Depends On      : None
Validated By    : SHA-256 Sum
"#;

        let sys = MockSys::new();
        let pacman = Pacman::new(&sys);
        let pkgs = pacman.parse_info_output(raw_si);

        assert_eq!(pkgs.len(), 2);
        let yakuake = pkgs.get("yakuake").unwrap();
        assert_eq!(yakuake.repository, "extra");
        assert_eq!(yakuake.version, "24.02.2-1");
        assert_eq!(yakuake.depends, vec!["konsole", "kwayland", "kxmlgui"]);

        let konsole = pkgs.get("konsole").unwrap();
        assert_eq!(konsole.depends.len(), 0);
    }

}
