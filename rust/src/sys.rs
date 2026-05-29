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

pub struct MockSys {
    pub commands: std::cell::RefCell<HashMap<String, Result<(i32, String, String), String>>>,
    pub http: std::cell::RefCell<HashMap<String, Result<String, String>>>,
}

impl MockSys {
    pub fn new() -> Self {
        Self {
            commands: std::cell::RefCell::new(HashMap::new()),
            http: std::cell::RefCell::new(HashMap::new()),
        }
    }
}

impl SysInterface for MockSys {
    fn run_command(&self, cmd: &str, args: &[&str]) -> Result<(i32, String, String), String> {
        let key = format!("{} {}", cmd, args.join(" "));
        if let Some(res) = self.commands.borrow().get(&key) {
            res.clone()
        } else {
            Err(format!("Mock command not found: {}", key))
        }
    }

    fn http_get(&self, url: &str, params: &[(&str, &str)]) -> Result<String, String> {
        let mut key = url.to_string();
        if !params.is_empty() {
            key.push('?');
            let query = params.iter().map(|(k, v)| format!("{}={}", k, v)).collect::<Vec<_>>().join("&");
            key.push_str(&query);
        }
        if let Some(res) = self.http.borrow().get(&key) {
            res.clone()
        } else {
            Err(format!("Mock HTTP not found: {}", key))
        }
    }
}
