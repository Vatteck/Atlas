use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{HashMap, HashSet};

pub mod sys;
pub mod pacman;

const KNOWN_LIST_FIELDS: &[&str] = &[
    "validpgpkeys", "checkdepends", "checkdepends_x86_64", "checkdepends_i686",
    "depends", "depends_x86_64", "depends_i686", "optdepends", "optdepends_x86_64",
    "optdepends_i686", "sha256sums", "sha256sums_x86_64", "sha512sums",
    "sha512sums_x86_64", "source", "source_x86_64", "source_i686",
    "makedepends", "makedepends_x86_64", "makedepends_i686", "provides", "conflicts"
];

#[derive(Debug, Clone)]
enum Val {
    Single(String),
    Multiple(HashSet<String>),
}

#[pyfunction]
#[pyo3(signature = (string, pkgname=None, fields=None))]
fn map_srcinfo(py: Python, string: &str, pkgname: Option<&str>, fields: Option<HashSet<String>>) -> PyResult<PyObject> {
    let mut subinfos: Vec<HashMap<String, Val>> = Vec::new();
    let mut subinfo: HashMap<String, Val> = HashMap::new();

    let is_list_field = |key: &str| -> bool {
        KNOWN_LIST_FIELDS.contains(&key)
    };

    for line in string.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        if let Some((key, val)) = line.split_once('=') {
            let key = key.trim();
            let val = val.trim();

            if (key == "pkgname" || key == "pkgbase") && !subinfo.is_empty() {
                subinfos.push(subinfo);
                subinfo = HashMap::new();
            }

            if fields.is_none() || fields.as_ref().unwrap().contains(key) {
                let s_val = val.to_string();
                
                subinfo.entry(key.to_string())
                    .and_modify(|e| match e {
                        Val::Single(s) => {
                            let mut set = HashSet::new();
                            set.insert(s.clone());
                            set.insert(s_val.clone());
                            *e = Val::Multiple(set);
                        }
                        Val::Multiple(set) => {
                            set.insert(s_val.clone());
                        }
                    })
                    .or_insert_with(|| {
                        if is_list_field(key) {
                            let mut set = HashSet::new();
                            set.insert(s_val);
                            Val::Multiple(set)
                        } else {
                            Val::Single(s_val)
                        }
                    });
            }
        }
    }

    if !subinfo.is_empty() {
        subinfos.push(subinfo);
    }

    let mut pkgnames = HashSet::new();
    for sub in &subinfos {
        if let Some(Val::Single(name)) = sub.get("pkgname") {
            pkgnames.insert(name.clone());
        }
    }

    let resolved_pkgname = if let Some(pn) = pkgname {
        if pkgnames.len() == 1 || !pkgnames.contains(pn) {
            None
        } else {
            Some(pn.to_string())
        }
    } else {
        None
    };

    let mut info: HashMap<String, Val> = HashMap::new();

    for sub in subinfos {
        let current_pkgname = match sub.get("pkgname") {
            Some(Val::Single(name)) => Some(name.clone()),
            _ => None,
        };

        let matches_pkgname = match &resolved_pkgname {
            Some(pn) => current_pkgname.is_none() || current_pkgname.as_ref() == Some(pn),
            None => true,
        };

        if matches_pkgname {
            for (key, val) in sub {
                if fields.is_none() || fields.as_ref().unwrap().contains(&key) {
                    info.entry(key)
                        .and_modify(|e| match e {
                            Val::Single(s) => {
                                let mut set = HashSet::new();
                                set.insert(s.clone());
                                match &val {
                                    Val::Single(v) => { set.insert(v.clone()); },
                                    Val::Multiple(vs) => { set.extend(vs.clone()); }
                                }
                                *e = Val::Multiple(set);
                            }
                            Val::Multiple(set) => {
                                match &val {
                                    Val::Single(v) => { set.insert(v.clone()); },
                                    Val::Multiple(vs) => { set.extend(vs.clone()); }
                                }
                            }
                        })
                        .or_insert(val);
                }
            }
        }
    }

    let dict = PyDict::new(py);
    for (k, v) in info {
        match v {
            Val::Single(s) => dict.set_item(k, s)?,
            Val::Multiple(set) => {
                let pylist = PyList::new(py, set.into_iter());
                dict.set_item(k, pylist)?;
            }
        }
    }

    Ok(dict.into())
}

#[pymodule]
fn atlas_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(map_srcinfo, m)?)?;
    Ok(())
}
