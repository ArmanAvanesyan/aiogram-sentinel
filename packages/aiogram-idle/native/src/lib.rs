//! Optional deterministic core. Application code owns time, random IDs, I/O and locks.
pub mod core;
pub mod queue;
use num_bigint::BigUint;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyModule;

pyo3::create_exception!(_aiogram_idle_native, OwnershipLost, PyRuntimeError);
pub const API_VERSION: u32 = 1;
pub const ENGINE_VERSION: &str = "0.3.1";
fn invalid(message: impl Into<String>) -> PyErr {
    PyValueError::new_err(message.into())
}
fn integer(raw: &str, zero: bool) -> PyResult<BigUint> {
    if raw.is_empty()
        || !raw
            .bytes()
            .all(|x| x.is_ascii_digit() || (b'a'..=b'f').contains(&x))
        || (raw.len() > 1 && raw.starts_with('0'))
        || (!zero && raw == "0")
    {
        return Err(invalid(
            "expected canonical nonnegative hexadecimal integer",
        ));
    }
    BigUint::parse_bytes(raw.as_bytes(), 16).ok_or_else(|| invalid("invalid integer"))
}
fn domain(error: &str) -> PyErr {
    if error == "ownership" {
        OwnershipLost::new_err("deadline claim expired or replaced")
    } else {
        invalid(error)
    }
}
fn times(values: &[f64]) -> PyResult<()> {
    if values.iter().all(|value| value.is_finite()) {
        Ok(())
    } else {
        Err(invalid("clock and expiry values must be finite"))
    }
}
#[pyfunction]
fn phase_transition(phase: &str, trigger: &str) -> PyResult<&'static str> {
    core::transition(phase, trigger).ok_or_else(|| invalid("invalid idle transition"))
}
#[pyfunction]
fn fingerprint_canonical(raw: &str) -> String {
    core::digest(raw)
}
#[pyfunction]
fn receipt_admission(
    existing: Option<&str>,
    digest: &str,
    retained_count: &str,
    limit: &str,
) -> PyResult<&'static str> {
    let count = integer(retained_count, true)?;
    let capacity = integer(limit, false)?;
    if digest.is_empty() {
        return Err(invalid("digest and positive receipt capacity required"));
    }
    Ok(match existing {
        Some(value) if value != digest => "conflict",
        Some(_) => "duplicate",
        None if count >= capacity => "capacity",
        None => "admit",
    })
}
#[pyfunction]
fn activity_guard(
    actual: Option<(String, String, String, f64)>,
    expected: (String, String, String),
    now: f64,
) -> PyResult<Option<&'static str>> {
    times(&[now])?;
    integer(&expected.2, false)?;
    if expected.0.is_empty() || expected.1.is_empty() || expected.2 == "0" {
        return Err(invalid("invalid activity guard"));
    }
    if let Some(value) = &actual {
        times(&[value.3])?;
        integer(&value.2, false)?;
    }
    Ok(core::activity(
        actual
            .as_ref()
            .map(|x| (x.0.as_str(), x.1.as_str(), x.2.as_str(), x.3)),
        (&expected.0, &expected.1, expected.2.as_str()),
        now,
    ))
}
#[pyfunction]
fn session_guard(
    actual: Option<(String, String, f64)>,
    expected: Option<(String, String)>,
    now: f64,
) -> PyResult<Option<&'static str>> {
    times(&[now])?;
    if let Some(value) = &actual {
        times(&[value.2])?;
        integer(&value.1, false)?;
    }
    if let Some(value) = &expected {
        integer(&value.1, false)?;
    }
    Ok(core::session(
        actual.as_ref().map(|x| (x.0.as_str(), x.1.as_str(), x.2)),
        expected.as_ref().map(|x| (x.0.as_str(), x.1.as_str())),
        now,
    ))
}
#[pyfunction]
fn claim_guard(
    actual: Option<(String, String, f64)>,
    expected: (String, String),
    now: f64,
) -> PyResult<Option<&'static str>> {
    times(&[now])?;
    if let Some(value) = &actual {
        times(&[value.2])?;
        integer(&value.1, false)?;
    }
    integer(&expected.1, false)?;
    Ok(core::claim(
        actual.as_ref().map(|x| (x.0.as_str(), x.1.as_str(), x.2)),
        (&expected.0, expected.1.as_str()),
        now,
    ))
}

type ClaimTuple = (String, String, String, f64, f64);
fn claim(value: queue::Claim) -> ClaimTuple {
    (value.0, value.1, value.2.to_str_radix(16), value.3, value.4)
}

type JobTuple = (String, f64, f64, Option<String>, f64);
fn job(value: queue::Job) -> JobTuple {
    (
        value.generation.to_str_radix(16),
        value.deadline,
        value.eligible,
        value.token,
        value.lease,
    )
}

#[pyclass(module = "aiogram_idle_native._aiogram_idle_native")]
#[derive(Default)]
struct DeadlineCore {
    state: queue::Queue,
}
#[pymethods]
impl DeadlineCore {
    #[new]
    fn new() -> Self {
        Self::default()
    }
    #[getter]
    fn sequence(&self) -> String {
        self.state.sequence.to_str_radix(16)
    }
    #[setter]
    fn set_sequence(&mut self, value: &str) -> PyResult<()> {
        self.state.sequence = integer(value, true)?;
        Ok(())
    }
    fn __len__(&self) -> usize {
        self.state.jobs.len()
    }
    fn heap_len(&self) -> usize {
        self.state.len_heap()
    }
    fn heap(&self) -> Vec<(f64, String, String)> {
        self.state
            .heap()
            .into_iter()
            .map(|(at, seq, key)| (at, seq.to_str_radix(16), key))
            .collect()
    }
    fn keys(&self) -> Vec<String> {
        self.state.keys()
    }
    fn get(&self, key: &str) -> Option<JobTuple> {
        self.state.jobs.get(key).cloned().map(job)
    }
    fn remove(&mut self, key: &str) -> Option<JobTuple> {
        self.state.jobs.remove(key).map(job)
    }
    fn clear(&mut self) {
        self.state.jobs.clear();
    }
    #[pyo3(signature=(key, namespace, bot_id, generation, deadline, eligible_at, token=None, lease_until=0.0))]
    #[allow(clippy::too_many_arguments)]
    fn put(
        &mut self,
        key: String,
        namespace: String,
        bot_id: String,
        generation: &str,
        deadline: f64,
        eligible_at: f64,
        token: Option<String>,
        lease_until: f64,
    ) -> PyResult<()> {
        self.state
            .put(
                key,
                namespace,
                bot_id,
                integer(generation, false)?,
                deadline,
                eligible_at,
                token,
                lease_until,
            )
            .map_err(domain)
    }
    fn push(&mut self, key: &str) -> PyResult<()> {
        self.state.push(key).map_err(domain)
    }
    #[pyo3(signature=(key, namespace, bot_id, deadline, preserve_token=None))]
    fn schedule(
        &mut self,
        key: String,
        namespace: String,
        bot_id: String,
        deadline: Option<f64>,
        preserve_token: Option<&str>,
    ) -> PyResult<()> {
        self.state
            .schedule(key, namespace, bot_id, deadline, preserve_token)
            .map_err(domain)
    }
    fn check(&self, key: &str, token: &str, generation: &str, now: f64) -> PyResult<JobTuple> {
        self.state
            .check(key, token, integer(generation, false)?, now)
            .map(job)
            .map_err(domain)
    }
    #[pyo3(signature=(limit, lease_seconds, now, tokens, namespace=None, bot_id=None))]
    fn claim(
        &mut self,
        limit: usize,
        lease_seconds: f64,
        now: f64,
        tokens: Vec<String>,
        namespace: Option<&str>,
        bot_id: Option<&str>,
    ) -> PyResult<Vec<ClaimTuple>> {
        self.state
            .claim(limit, lease_seconds, now, &tokens, namespace, bot_id)
            .map(|values| values.into_iter().map(claim).collect())
            .map_err(domain)
    }
    fn renew(
        &mut self,
        key: &str,
        token: &str,
        generation: &str,
        now: f64,
        lease_seconds: f64,
    ) -> PyResult<ClaimTuple> {
        self.state
            .renew(key, token, integer(generation, false)?, now, lease_seconds)
            .map(claim)
            .map_err(domain)
    }
    #[pyo3(signature=(key, token, generation, now, deadline=None))]
    fn release(
        &mut self,
        key: &str,
        token: &str,
        generation: &str,
        now: f64,
        deadline: Option<f64>,
    ) -> PyResult<()> {
        self.state
            .release(key, token, integer(generation, false)?, now, deadline)
            .map_err(domain)
    }
    fn reconcile(
        &mut self,
        candidates: Vec<(String, String, String, f64)>,
        limit: usize,
    ) -> PyResult<usize> {
        self.state.reconcile(candidates, limit).map_err(domain)
    }
}
#[pymodule]
fn _aiogram_idle_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("API_VERSION", API_VERSION)?;
    module.add("ENGINE_VERSION", ENGINE_VERSION)?;
    module.add("OwnershipLost", module.py().get_type::<OwnershipLost>())?;
    module.add_function(wrap_pyfunction!(phase_transition, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint_canonical, module)?)?;
    module.add_function(wrap_pyfunction!(receipt_admission, module)?)?;
    module.add_function(wrap_pyfunction!(activity_guard, module)?)?;
    module.add_function(wrap_pyfunction!(session_guard, module)?)?;
    module.add_function(wrap_pyfunction!(claim_guard, module)?)?;
    module.add_class::<DeadlineCore>()?;
    Ok(())
}
