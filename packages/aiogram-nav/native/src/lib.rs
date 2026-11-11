//! Deterministic data algorithms only. No Telegram, Redis, locks or business calls.
pub mod json;
pub mod registry;

use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

pub const API_VERSION: u32 = 1;
pub const ENGINE_VERSION: &str = "0.3.0";
fn invalid(error: impl ToString) -> PyErr {
    PyValueError::new_err(error.to_string())
}

fn to_python(py: Python<'_>, value: &Value) -> PyResult<Py<PyAny>> {
    Ok(match value {
        Value::Null => py.None(),
        Value::Bool(x) => x.into_pyobject(py)?.to_owned().into_any().unbind(),
        Value::String(x) => x.into_pyobject(py)?.into_any().unbind(),
        Value::Number(x) => {
            let text = x.to_string();
            if text.contains(['.', 'e', 'E']) {
                x.as_f64()
                    .ok_or_else(|| invalid("Non-finite JSON number"))?
                    .into_pyobject(py)?
                    .into_any()
                    .unbind()
            } else if let Ok(value) = text.parse::<i64>() {
                value.into_pyobject(py)?.into_any().unbind()
            } else if let Ok(value) = text.parse::<u64>() {
                value.into_pyobject(py)?.into_any().unbind()
            } else {
                // Preserve Python's unbounded integers and configured digit limit.
                PyModule::import(py, "builtins")?
                    .getattr("int")?
                    .call1((text,))?
                    .unbind()
            }
        }
        Value::Array(xs) => {
            let out = PyList::empty(py);
            for x in xs {
                out.append(to_python(py, x)?)?;
            }
            out.into_any().unbind()
        }
        Value::Object(xs) => {
            let out = PyDict::new(py);
            for (key, value) in xs {
                out.set_item(key, to_python(py, value)?)?;
            }
            out.into_any().unbind()
        }
    })
}

#[pyfunction]
#[pyo3(signature=(raw, max_bytes=8_388_608, max_depth=64))]
fn strict_loads(
    py: Python<'_>,
    raw: &str,
    max_bytes: usize,
    max_depth: usize,
) -> PyResult<Py<PyAny>> {
    let value = json::parse(raw, max_bytes, max_depth).map_err(invalid)?;
    to_python(py, &value)
}

#[pyfunction]
#[pyo3(signature=(raw, max_bytes=8_388_608, max_depth=64))]
fn validate_json(raw: &str, max_bytes: usize, max_depth: usize) -> PyResult<()> {
    json::parse(raw, max_bytes, max_depth)
        .map(|_| ())
        .map_err(invalid)
}

/// Hash only the exact canonical bytes supplied by the Python policy layer.
/// No Rust JSON reserialization is allowed to alter durable receipt identity.
pub fn canonical_digest(raw: &str) -> String {
    format!("{:x}", Sha256::digest(raw.as_bytes()))
}
#[pyfunction]
fn fingerprint_canonical(raw: &str) -> String {
    canonical_digest(raw)
}

#[pyclass(frozen, module = "aiogram_nav_native._aiogram_nav_native")]
struct Registry {
    graph: registry::Graph,
}
#[pymethods]
impl Registry {
    #[new]
    fn new(raw: &str) -> PyResult<Self> {
        Ok(Self {
            graph: registry::Graph::compile(raw).map_err(invalid)?,
        })
    }
    fn ancestors(&self, id: &str) -> PyResult<Vec<String>> {
        self.graph.ancestors(id).map_err(PyKeyError::new_err)
    }
    fn root_for(&self, id: &str) -> PyResult<String> {
        self.graph.root(id).map_err(PyKeyError::new_err)
    }
    fn back_target(&self, id: &str) -> PyResult<Option<String>> {
        self.graph
            .nodes
            .get(id)
            .map(|n| n.back_to.clone())
            .ok_or_else(|| PyKeyError::new_err("Unknown node"))
    }
    fn cancel_target(&self, id: &str) -> PyResult<String> {
        self.graph
            .cancel
            .get(id)
            .cloned()
            .ok_or_else(|| PyKeyError::new_err("Unknown node"))
    }
    fn resolve(&self, id: &str) -> PyResult<String> {
        self.graph.resolve(id).map_err(PyKeyError::new_err)
    }
    fn node_count(&self) -> usize {
        self.graph.nodes.len()
    }
}

pub fn history(
    raw: &str,
    current: Option<&str>,
    mode: &str,
    limit: usize,
    pop: usize,
    push_current: bool,
) -> Result<String, String> {
    if limit > 1000 || pop > 1000 {
        return Err("History exceeds bounded capacity".into());
    }
    let Value::Array(mut items) = json::parse(raw, 8_388_608, 64)? else {
        return Err("History must be an array".into());
    };
    match mode {
        "push" => {
            if push_current {
                if let Some(raw) = current {
                    items.push(json::parse(raw, 8_388_608, 64)?);
                }
            }
        }
        "pop" => {
            items.truncate(items.len().saturating_sub(pop));
        }
        "clear" => items.clear(),
        "none" => (),
        _ => return Err("Unknown history mode".into()),
    }
    if limit == 0 {
        items.clear();
    } else if items.len() > limit {
        items.drain(..items.len() - limit);
    }
    serde_json::to_string(&items).map_err(|_| "History serialization failed".into())
}
#[pyfunction]
#[pyo3(signature=(history_json, current_entry_json, mode, limit, pop=1, push_current=true))]
fn transition_history(
    history_json: &str,
    current_entry_json: Option<&str>,
    mode: &str,
    limit: usize,
    pop: usize,
    push_current: bool,
) -> PyResult<String> {
    history(
        history_json,
        current_entry_json,
        mode,
        limit,
        pop,
        push_current,
    )
    .map_err(invalid)
}

fn integer(raw: &str) -> Result<(bool, &str), String> {
    let (negative, digits) = raw.strip_prefix('-').map_or((false, raw), |d| (true, d));
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return Err("Expected decimal integer".into());
    }
    let digits = digits.trim_start_matches('0');
    Ok((
        negative && !digits.is_empty(),
        if digits.is_empty() { "0" } else { digits },
    ))
}
fn compare(left: &str, right: &str) -> Result<std::cmp::Ordering, String> {
    let (ln, l) = integer(left)?;
    let (rn, r) = integer(right)?;
    Ok(if ln != rn {
        if ln {
            std::cmp::Ordering::Less
        } else {
            std::cmp::Ordering::Greater
        }
    } else {
        let result = l.len().cmp(&r.len()).then_with(|| l.cmp(r));
        if ln {
            result.reverse()
        } else {
            result
        }
    })
}
fn increment(raw: &str) -> Result<String, String> {
    let (negative, digits) = integer(raw)?;
    if negative {
        return Err("Expected non-negative state integer".into());
    }
    let mut out = digits.as_bytes().to_vec();
    for byte in out.iter_mut().rev() {
        if *byte < b'9' {
            *byte += 1;
            return String::from_utf8(out).map_err(|_| "Invalid integer".into());
        }
        *byte = b'0';
    }
    out.insert(0, b'1');
    String::from_utf8(out).map_err(|_| "Invalid integer".into())
}
fn number(raw: &str) -> Result<Value, String> {
    integer(raw)?;
    serde_json::from_str(raw).map_err(|_| "Invalid canonical integer".into())
}
#[pyfunction]
#[pyo3(signature=(old_json, node_id, params_changed, accepted_activity, now_ms))]
fn transition_state(
    old_json: Option<&str>,
    node_id: &str,
    params_changed: bool,
    accepted_activity: bool,
    now_ms: &str,
) -> PyResult<String> {
    if integer(now_ms).map_err(invalid)?.0 {
        return Err(invalid("Negative transition timestamp"));
    }
    let old = old_json
        .map(|s| json::parse(s, 8_388_608, 64))
        .transpose()
        .map_err(invalid)?;
    let read = |name: &str| -> PyResult<String> {
        let raw = old
            .as_ref()
            .and_then(|o| o.get(name))
            .and_then(Value::as_number)
            .map(ToString::to_string)
            .ok_or_else(|| invalid("Malformed previous state"))?;
        if integer(&raw).map_err(invalid)?.0 {
            return Err(invalid("Negative previous state"));
        }
        Ok(raw)
    };
    let same = old
        .as_ref()
        .is_some_and(|o| o.get("node_id").and_then(Value::as_str) == Some(node_id));
    let (nav, activity, entered, last) = if old.is_some() {
        (
            increment(&read("nav_revision")?).map_err(invalid)?,
            if accepted_activity {
                increment(&read("activity_revision")?).map_err(invalid)?
            } else {
                read("activity_revision")?
            },
            if same && !params_changed {
                read("entered_at")?
            } else {
                now_ms.to_owned()
            },
            if accepted_activity {
                now_ms.to_owned()
            } else {
                read("last_activity_at")?
            },
        )
    } else {
        ("1".into(), "1".into(), now_ms.into(), now_ms.into())
    };
    Ok(json!({"nav_revision":number(&nav).map_err(invalid)?,"activity_revision":number(&activity).map_err(invalid)?,"entered_at":number(&entered).map_err(invalid)?,"last_activity_at":number(&last).map_err(invalid)?}).to_string())
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn token_matches(
    token_key: &str,
    current_key: &str,
    token_actor: &str,
    actor: &str,
    token_session: &str,
    current_session: &str,
    token_view: &str,
    current_view: &str,
    expires_at: &str,
    now_ms: &str,
) -> PyResult<bool> {
    Ok(token_key == current_key
        && compare(token_actor, actor).map_err(invalid)? == std::cmp::Ordering::Equal
        && token_session == current_session
        && token_view == current_view
        && compare(expires_at, now_ms).map_err(invalid)? == std::cmp::Ordering::Greater)
}

#[pymodule]
fn _aiogram_nav_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("API_VERSION", API_VERSION)?;
    module.add("ENGINE_VERSION", ENGINE_VERSION)?;
    module.add_function(wrap_pyfunction!(strict_loads, module)?)?;
    module.add_function(wrap_pyfunction!(validate_json, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint_canonical, module)?)?;
    module.add_function(wrap_pyfunction!(transition_history, module)?)?;
    module.add_function(wrap_pyfunction!(transition_state, module)?)?;
    module.add_function(wrap_pyfunction!(token_matches, module)?)?;
    module.add_class::<Registry>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn strict_json_rejects_duplicates_and_overflow() {
        for raw in [
            r#"{"a":1,"a":2}"#,
            r#"{"a":1,"\u0061":2}"#,
            "NaN",
            "1e400",
            r#""\ud800""#,
            "[1,]",
            "01",
        ] {
            assert!(json::parse(raw, 1024, 64).is_err(), "{raw}");
        }
    }
    #[test]
    fn strict_json_preserves_unbounded_integer_lexemes() {
        let raw = "1234567890123456789012345678901234567890";
        assert_eq!(json::parse(raw, 1024, 64).unwrap().to_string(), raw);
        assert!(json::parse("[[[0]]]", 1024, 2).is_err());
    }
    #[test]
    fn bounded_history_and_decimal_transitions() {
        assert_eq!(
            history("[1,2]", Some("3"), "push", 2, 1, true).unwrap(),
            "[2,3]"
        );
        assert_eq!(history("[1,2]", None, "pop", 2, 10, false).unwrap(), "[]");
        assert_eq!(
            increment("99999999999999999999999999999999").unwrap(),
            "100000000000000000000000000000000"
        );
        assert_eq!(
            compare("-99999999999999999999999999999999", "-1").unwrap(),
            std::cmp::Ordering::Less
        );
    }
    #[test]
    fn exact_fingerprint_known_vector() {
        assert_eq!(
            canonical_digest("abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }
    #[test]
    fn graph_cycle_and_cached_parent_validation() {
        let valid = r#"{"roots":["main"],"nodes":[{"id":"main","renderer":"r"},{"id":"child","parent":"main","renderer":"r"}],"migrations":{},"safe_root":null}"#;
        let graph = registry::Graph::compile(valid).unwrap();
        assert_eq!(graph.root("child").unwrap(), "main");
        assert_eq!(graph.roots(), 1);
        assert!(registry::Graph::compile(
            &valid.replace("\"parent\":\"main\"", "\"parent\":\"child\"")
        )
        .is_err());
    }
}
