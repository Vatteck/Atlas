use crate::sys::SysInterface;
use std::collections::{BTreeSet, HashMap, HashSet};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct PacmanPackage {
    pub name: String,
    pub repository: String,
    pub version: String,
    pub depends: Vec<String>,
    pub provides: Vec<String>,
    pub conflicts: Vec<String>,
    pub description: Option<String>,
    pub download_size: Option<f64>,
    pub installed_size: Option<f64>,
}

/// Convert a human-readable size (e.g. `12.5`, `"MiB"`) to bytes, mirroring
/// `atlas.commons.util.size_to_byte`: base 1024 when the unit ends in `ib`,
/// otherwise 1000; `b` is bits (÷8) and `B` is bytes.
pub fn size_to_byte(num: f64, unit: &str) -> f64 {
    let lower = unit.trim().to_lowercase();

    if unit == "b" {
        return num / 8.0;
    }
    if unit == "B" {
        return num;
    }

    let base: f64 = if lower.ends_with("ib") {
        1024.0
    } else {
        1000.0
    };

    match lower.chars().next() {
        Some('k') => num * base,
        Some('m') => num * base.powi(2),
        Some('g') => num * base.powi(3),
        Some('t') => num * base.powi(4),
        _ => num * base.powi(5),
    }
}

impl PacmanPackage {
    /// Emit the canonical `deps_data` schema consumed by the Python side
    /// (`d`/`p`/`r`/`v`/`s`/`ds`/`c`/`des`). Empty `d`/`c` become `null` (matching the
    /// Python `None`). `des` is only included when `include_description` is true, mirroring
    /// `pacman.py:map_updates_data`'s `description` flag. See
    /// `docs/plans/2026-05-28-deps-data-schema-fix-design.md`.
    pub fn to_deps_data(&self, include_description: bool) -> serde_json::Value {
        // Version with any `=constraint` suffix stripped, matching pacman.py.
        let v_clean = self.version.split('=').next().unwrap_or("").to_string();

        // Provides always carries the package's own name and name=version.
        let mut provides: BTreeSet<String> = BTreeSet::new();
        provides.insert(self.name.clone());
        provides.insert(format!("{}={}", self.name, v_clean));
        for p in &self.provides {
            provides.insert(p.clone());
            if let Some((base, _)) = p.split_once('=') {
                provides.insert(base.to_string());
            }
        }

        let depends: BTreeSet<String> = self.depends.iter().cloned().collect();
        let conflicts: BTreeSet<String> = self.conflicts.iter().cloned().collect();

        serde_json::json!({
            "r": self.repository,
            "v": v_clean,
            "d": if depends.is_empty() {
                serde_json::Value::Null
            } else {
                serde_json::json!(depends.into_iter().collect::<Vec<_>>())
            },
            "p": provides.into_iter().collect::<Vec<_>>(),
            "c": if conflicts.is_empty() {
                serde_json::Value::Null
            } else {
                serde_json::json!(conflicts.into_iter().collect::<Vec<_>>())
            },
            "s": self.installed_size,
            "ds": self.download_size,
            "des": if include_description { serde_json::json!(self.description) } else { serde_json::Value::Null },
        })
    }
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

    pub fn read_package_info(
        &self,
        pkgs: &[&str],
    ) -> Result<HashMap<String, PacmanPackage>, String> {
        if pkgs.is_empty() {
            return Ok(HashMap::new());
        }
        let mut args = vec!["-Si"];
        args.extend(pkgs);
        let (_, stdout, _) = self.sys.run_command("pacman", &args)?;
        Ok(parse_info_output(&stdout))
    }
}

/// Parse `pacman -Si` / `-Qi` output into packages keyed by name. Free function (no
/// system access) so it can back the pure `parse_pacman_info` PyO3 entry point and be
/// unit/benchmark-tested directly.
pub fn parse_info_output(output: &str) -> HashMap<String, PacmanPackage> {
    let mut result = HashMap::new();
    let mut current_fields: HashMap<String, String> = HashMap::new();
    let mut last_field = String::new();

    let commit_package = |fields: &mut HashMap<String, String>,
                          res: &mut HashMap<String, PacmanPackage>| {
        if let Some(name) = fields.get("Name").map(|s| s.trim().to_string()) {
            if !name.is_empty() {
                let parse_list = |f_name: &str| -> Vec<String> {
                    fields
                        .get(f_name)
                        .map(|val| {
                            val.split_whitespace()
                                .map(|s| s.trim().to_string())
                                .filter(|s| !s.is_empty() && s.to_lowercase() != "none")
                                .collect()
                        })
                        .unwrap_or_else(Vec::new)
                };

                let parse_size = |f_name: &str| -> Option<f64> {
                    let val = fields.get(f_name)?;
                    let mut it = val.split_whitespace();
                    let num = it.next()?.replace(',', ".");
                    let unit = it.next().unwrap_or("B");
                    let num: f64 = num.parse().ok()?;
                    Some(size_to_byte(num, unit))
                };

                let description = fields
                    .get("Description")
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty());

                let pkg = PacmanPackage {
                    name: name.clone(),
                    repository: fields.get("Repository").cloned().unwrap_or_default(),
                    version: fields.get("Version").cloned().unwrap_or_default(),
                    depends: parse_list("Depends On"),
                    provides: parse_list("Provides"),
                    conflicts: parse_list("Conflicts With"),
                    description,
                    download_size: parse_size("Download Size"),
                    installed_size: parse_size("Installed Size"),
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_info_output() {
        let raw_si = r#"Repository      : extra
Name            : yakuake
Version         : 24.02.2-1
Description     : A drop-down terminal emulator
Provides        : None
Depends On      : konsole  kwayland
                  kxmlgui
Conflicts With  : None
Download Size   : 1024.00 KiB
Installed Size  : 2.00 MiB
Validated By    : SHA-256 Sum

Repository      : extra
Name            : konsole
Version         : 24.02.2-1
Depends On      : None
Validated By    : SHA-256 Sum
"#;

        let pkgs = parse_info_output(raw_si);

        assert_eq!(pkgs.len(), 2);
        let yakuake = pkgs.get("yakuake").unwrap();
        assert_eq!(yakuake.repository, "extra");
        assert_eq!(yakuake.version, "24.02.2-1");
        assert_eq!(yakuake.depends, vec!["konsole", "kwayland", "kxmlgui"]);
        assert_eq!(
            yakuake.description.as_deref(),
            Some("A drop-down terminal emulator")
        );
        assert_eq!(yakuake.download_size, Some(1024.0 * 1024.0));
        assert_eq!(yakuake.installed_size, Some(2.0 * 1024.0 * 1024.0));

        let konsole = pkgs.get("konsole").unwrap();
        assert_eq!(konsole.depends.len(), 0);
        assert_eq!(konsole.download_size, None);
    }

    #[test]
    fn test_size_to_byte() {
        assert_eq!(size_to_byte(1.0, "B"), 1.0);
        assert_eq!(size_to_byte(1.0, "KiB"), 1024.0);
        assert_eq!(size_to_byte(1.0, "MiB"), 1024.0 * 1024.0);
        assert_eq!(size_to_byte(1.0, "kB"), 1000.0);
        assert_eq!(size_to_byte(1.0, "MB"), 1_000_000.0);
        assert_eq!(size_to_byte(8.0, "b"), 1.0);
    }

    #[test]
    fn test_to_deps_data_schema() {
        let pkg = PacmanPackage {
            name: "yakuake".to_string(),
            repository: "extra".to_string(),
            version: "24.02.2-1".to_string(),
            depends: vec!["konsole".to_string(), "kxmlgui".to_string()],
            provides: vec!["dropdown-terminal".to_string(), "yakuake-abi=2".to_string()],
            conflicts: vec![],
            description: Some("Terminal".to_string()),
            download_size: Some(1024.0),
            installed_size: Some(2048.0),
        };

        let data = pkg.to_deps_data(true);

        assert_eq!(data["r"], "extra");
        assert_eq!(data["v"], "24.02.2-1");
        assert_eq!(data["des"], "Terminal");
        assert_eq!(data["s"], 2048.0);
        assert_eq!(data["ds"], 1024.0);
        // conflicts empty -> null
        assert!(data["c"].is_null());

        let depends: Vec<&str> = data["d"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        assert_eq!(depends, vec!["konsole", "kxmlgui"]);

        // provides must include name, name=version, raw provides, and base of versioned provide
        let provides: Vec<&str> = data["p"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        for expected in [
            "yakuake",
            "yakuake=24.02.2-1",
            "dropdown-terminal",
            "yakuake-abi=2",
            "yakuake-abi",
        ] {
            assert!(
                provides.contains(&expected),
                "missing provide: {} in {:?}",
                expected,
                provides
            );
        }
    }

    #[test]
    fn test_to_deps_data_description_flag_and_empty_nulls() {
        let pkg = PacmanPackage {
            name: "konsole".to_string(),
            repository: "extra".to_string(),
            version: "24.02.2-1".to_string(),
            depends: vec![],
            provides: vec![],
            conflicts: vec![],
            description: Some("A terminal".to_string()),
            download_size: Some(1.0),
            installed_size: Some(2.0),
        };

        // description gated off -> des null; empty depends/conflicts -> null
        let off = pkg.to_deps_data(false);
        assert!(off["des"].is_null());
        assert!(off["d"].is_null());
        assert!(off["c"].is_null());
        // provides always carries name + name=version
        let p: Vec<&str> = off["p"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        assert!(p.contains(&"konsole") && p.contains(&"konsole=24.02.2-1"));

        // description gated on -> des present
        let on = pkg.to_deps_data(true);
        assert_eq!(on["des"], "A terminal");
    }
}
