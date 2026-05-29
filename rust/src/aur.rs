use crate::sys::SysInterface;
use std::collections::HashMap;

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
}
