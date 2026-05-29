use crate::sys::SysInterface;
use std::collections::{BTreeSet, HashMap};

#[derive(serde::Deserialize, serde::Serialize, Clone, Debug, PartialEq)]
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

impl AurPackageRaw {
    /// Emit the canonical `deps_data` schema for an AUR package, mirroring
    /// `aur.py:map_update_data`: `r="aur"`, sizes/description null (the RPC info
    /// endpoint does not provide them). See
    /// `docs/plans/2026-05-28-deps-data-schema-fix-design.md`.
    pub fn to_deps_data(&self) -> serde_json::Value {
        let mut provides: BTreeSet<String> = BTreeSet::new();
        provides.insert(self.name.clone());
        provides.insert(format!("{}={}", self.name, self.version));
        if let Some(ps) = &self.provides {
            for p in ps {
                provides.insert(p.clone());
                if let Some((base, _)) = p.split_once('=') {
                    provides.insert(base.to_string());
                }
            }
        }

        let depends: BTreeSet<String> = self.depends.clone().unwrap_or_default()
            .into_iter().collect();
        let conflicts: BTreeSet<String> = self.conflicts.clone().unwrap_or_default()
            .into_iter().collect();

        serde_json::json!({
            "r": "aur",
            "v": self.version,
            "d": depends.into_iter().collect::<Vec<_>>(),
            "p": provides.into_iter().collect::<Vec<_>>(),
            "c": if conflicts.is_empty() {
                serde_json::Value::Null
            } else {
                serde_json::json!(conflicts.into_iter().collect::<Vec<_>>())
            },
            "s": serde_json::Value::Null,
            "ds": serde_json::Value::Null,
            "des": serde_json::Value::Null,
        })
    }
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
        if names.is_empty() {
            return Ok(HashMap::new());
        }
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sys::MockSys;

    #[test]
    fn test_aur_client_get_packages() {
        let sys = MockSys::new();
        let mock_json = r#"{
            "results": [
                {
                    "Name": "yakuake-git",
                    "Version": "24.02.2.r10.g12345",
                    "Depends": ["konsole", "kxmlgui"],
                    "MakeDepends": ["extra-cmake-modules"],
                    "Provides": ["yakuake"],
                    "Conflicts": ["yakuake"]
                }
            ]
        }"#;

        sys.http.borrow_mut().insert(
            "https://aur.archlinux.org/rpc/v5/info?arg[]=yakuake-git".to_string(),
            Ok(mock_json.to_string())
        );

        let client = AurClient::new(&sys);
        let pkgs = client.get_packages(&["yakuake-git"]).unwrap();

        assert_eq!(pkgs.len(), 1);
        let pkg = pkgs.get("yakuake-git").unwrap();
        assert_eq!(pkg.name, "yakuake-git");
        assert_eq!(pkg.version, "24.02.2.r10.g12345");
        assert_eq!(pkg.depends, Some(vec!["konsole".to_string(), "kxmlgui".to_string()]));
        assert_eq!(pkg.provides, Some(vec!["yakuake".to_string()]));
    }

    #[test]
    fn test_aur_to_deps_data_schema() {
        let pkg = AurPackageRaw {
            name: "yakuake-git".to_string(),
            version: "24.02.2.r10".to_string(),
            depends: Some(vec!["konsole".to_string()]),
            make_depends: Some(vec!["cmake".to_string()]),
            provides: Some(vec!["yakuake".to_string()]),
            conflicts: Some(vec!["yakuake".to_string()]),
        };

        let data = pkg.to_deps_data();

        assert_eq!(data["r"], "aur");
        assert_eq!(data["v"], "24.02.2.r10");
        // AUR RPC info gives no sizes/description
        assert!(data["s"].is_null());
        assert!(data["ds"].is_null());
        assert!(data["des"].is_null());

        let conflicts: Vec<&str> = data["c"].as_array().unwrap()
            .iter().map(|v| v.as_str().unwrap()).collect();
        assert_eq!(conflicts, vec!["yakuake"]);

        let provides: Vec<&str> = data["p"].as_array().unwrap()
            .iter().map(|v| v.as_str().unwrap()).collect();
        for expected in ["yakuake-git", "yakuake-git=24.02.2.r10", "yakuake"] {
            assert!(provides.contains(&expected), "missing provide: {} in {:?}", expected, provides);
        }
    }

    #[test]
    fn test_aur_get_packages_empty_input() {
        let sys = MockSys::new();
        let client = AurClient::new(&sys);
        let pkgs = client.get_packages(&[]).unwrap();
        assert!(pkgs.is_empty());
    }
}
