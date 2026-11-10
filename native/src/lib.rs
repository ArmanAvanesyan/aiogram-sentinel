//! CPU-only native boundaries. Python resolves all translator callbacks first.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};

type Rows = Vec<(String, String)>;
type Profiles = Vec<(String, Vec<(String, Rows)>)>;
type Requests = Vec<(String, String, String, String, String)>;
type BatchResult = Vec<String>;

pub fn resolve_profile(include: &[String], exclude: &[String], known: &[String]) -> Vec<String> {
    let excluded: HashSet<&str> = exclude.iter().map(String::as_str).collect();
    let names: HashSet<&str> = known.iter().map(String::as_str).collect();
    include
        .iter()
        .filter(|name| names.contains(name.as_str()) && !excluded.contains(name.as_str()))
        .cloned()
        .collect()
}

pub fn validate_rows(rows: &[(String, String)]) -> Result<(), String> {
    for (name, description) in rows {
        let mut chars = name.bytes();
        if !(1..=32).contains(&name.len())
            || !chars.next().is_some_and(|c| c.is_ascii_lowercase())
            || !chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'_')
        {
            return Err("Invalid resolved command name".into());
        }
        if !(1..=256).contains(&description.chars().count()) {
            return Err("Invalid resolved command description".into());
        }
    }
    Ok(())
}

#[derive(Serialize)]
struct Command<'a> {
    command: &'a str,
    description: &'a str,
}

pub fn encode_rows(rows: &[(String, String)]) -> String {
    serde_json::to_string(
        &rows
            .iter()
            .map(|(command, description)| Command {
                command,
                description,
            })
            .collect::<Vec<_>>(),
    )
    .expect("strings always serialize")
}

pub fn fingerprint_encoded(
    bot: &str,
    scope: &str,
    language: &str,
    commands: &str,
) -> Result<String, String> {
    if bot.is_empty() || bot.starts_with('0') || !bot.bytes().all(|c| c.is_ascii_digit()) {
        return Err("A positive decimal bot identity is required".into());
    }
    // This boundary takes canonical Python-produced scope JSON. Retain legacy
    // Python NaN/Infinity spelling inside dictionaries rather than normalizing it.
    if !scope.starts_with('{') || !scope.ends_with('}') {
        return Err("Scope must be a canonical object".into());
    }
    let language_value: serde_json::Value =
        serde_json::from_str(language).map_err(|_| "Invalid language JSON")?;
    if !language_value.is_null() && !language_value.is_string() {
        return Err("Language must be string or null".into());
    }
    // Scope/language strings are canonicalized by Python, retaining its float,
    // arbitrary-integer and Unicode semantics without calling Python here.
    let value = format!(
        "{{\"bot_id\":{bot},\"commands\":{commands},\"language_code\":{language},\"scope\":{scope}}}"
    );
    Ok(format!("{:x}", Sha256::digest(value.as_bytes())))
}

#[pyclass(frozen)]
struct NativeSnapshot {
    profiles: HashMap<(String, String), (Rows, String)>,
}

#[pymethods]
impl NativeSnapshot {
    fn resolve_batch(&self, requests: Requests) -> PyResult<BatchResult> {
        let mut results = Vec::with_capacity(requests.len());
        for (profile, locale, bot, scope, language) in requests {
            let (_rows, encoded) = self
                .profiles
                .get(&(profile, locale))
                .ok_or_else(|| PyValueError::new_err("Unknown compiled profile/locale"))?;
            let hash = fingerprint_encoded(&bot, &scope, &language, encoded)
                .map_err(PyValueError::new_err)?;
            results.push(hash);
        }
        Ok(results)
    }
}

#[pyfunction(name = "resolve_profile")]
fn resolve_profile_py(
    include: Vec<String>,
    exclude: Vec<String>,
    known: Vec<String>,
) -> Vec<String> {
    resolve_profile(&include, &exclude, &known)
}
#[pyfunction]
fn validate_commands(rows: Rows) -> PyResult<()> {
    validate_rows(&rows).map_err(PyValueError::new_err)
}
#[pyfunction]
fn fingerprint(
    bot_id: String,
    scope_json: String,
    language_json: String,
    rows: Rows,
) -> PyResult<String> {
    fingerprint_encoded(&bot_id, &scope_json, &language_json, &encode_rows(&rows))
        .map_err(PyValueError::new_err)
}
#[pyfunction(name = "compile")]
fn compile_py(rows: Profiles) -> PyResult<NativeSnapshot> {
    let mut profiles = HashMap::new();
    for (profile, locales) in rows {
        for (locale, commands) in locales {
            validate_rows(&commands).map_err(PyValueError::new_err)?;
            let encoded = encode_rows(&commands);
            if profiles
                .insert((profile.clone(), locale), (commands, encoded))
                .is_some()
            {
                return Err(PyValueError::new_err("Duplicate profile/locale"));
            }
        }
    }
    Ok(NativeSnapshot { profiles })
}
#[pyfunction]
fn abi_version() -> u32 {
    1
}
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}
#[pymodule]
fn _aiogram_cmds_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_profile_py, module)?)?;
    module.add_function(wrap_pyfunction!(validate_commands, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint, module)?)?;
    module.add_function(wrap_pyfunction!(compile_py, module)?)?;
    module.add_function(wrap_pyfunction!(abi_version, module)?)?;
    module.add_function(wrap_pyfunction!(version, module)?)?;
    module.add_class::<NativeSnapshot>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preserves_duplicates_and_exclusions() {
        let input = vec!["a".into(), "a".into(), "b".into(), "missing".into()];
        assert_eq!(
            resolve_profile(&input, &["b".into()], &["a".into(), "b".into()]),
            vec!["a", "a"]
        );
    }
    #[test]
    fn validates_before_hashing() {
        assert!(validate_rows(&[("bad!".into(), "Description".into())]).is_err());
        assert!(fingerprint_encoded("0", "{}", "null", "[]").is_err());
        assert!(fingerprint_encoded("1", "[]", "null", "[]").is_err());
    }
}
