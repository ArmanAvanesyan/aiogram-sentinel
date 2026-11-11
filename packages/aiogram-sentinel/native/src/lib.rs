//! Synchronous, process-local storage. Clocks and interval validation belong to Python.
use std::collections::{HashMap, VecDeque};
use std::sync::Mutex;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

#[derive(Default)]
pub struct RateState {
    pub counters: HashMap<Vec<u8>, VecDeque<f64>>,
}

impl RateState {
    fn counter(&mut self, key: &[u8], window: f64, now: f64) -> &mut VecDeque<f64> {
        // Avoid allocating an owned key on every hit. Keys are copied only
        // for first admission; the extra lookup keeps std's randomized hasher.
        if !self.counters.contains_key(key) {
            self.counters.insert(key.to_owned(), VecDeque::new());
        }
        let counter = self.counters.get_mut(key).expect("admitted counter");
        let cutoff = now - window;
        // Exact-boundary requests remain in the window, matching Python deque.
        while counter.front().is_some_and(|value| *value < cutoff) {
            counter.pop_front();
        }
        counter
    }

    pub fn allow(&mut self, key: &[u8], maximum: usize, window: f64, now: f64) -> bool {
        let counter = self.counter(key, window, now);
        if counter.len() < maximum {
            counter.push_back(now);
            true
        } else {
            false
        }
    }

    pub fn remaining(&mut self, key: &[u8], maximum: usize, window: f64, now: f64) -> usize {
        maximum.saturating_sub(self.counter(key, window, now).len())
    }

    pub fn increment(&mut self, key: &[u8], window: f64, now: f64) -> usize {
        let counter = self.counter(key, window, now);
        counter.push_back(now);
        counter.len()
    }

    pub fn count(&mut self, key: &[u8], now: f64) -> usize {
        self.counter(key, 60.0, now).len()
    }

    pub fn reset(&mut self, key: &[u8]) {
        if let Some(counter) = self.counters.get_mut(key) {
            counter.clear();
        }
    }
}

#[derive(Default)]
pub struct DebounceState {
    pub entries: HashMap<Vec<u8>, f64>,
}

impl DebounceState {
    pub fn seen(&mut self, key: &[u8], window: f64, fingerprint: &[u8], now: f64) -> bool {
        // Preserve the legacy composite key and its interaction with raw-key helpers.
        let mut combined = Vec::with_capacity(key.len() + fingerprint.len() + 1);
        combined.extend_from_slice(key);
        combined.push(b':');
        combined.extend_from_slice(fingerprint);
        let key = combined;
        let timestamp = *self.entries.get(&key).unwrap_or(&0.0);
        if timestamp != 0.0 && timestamp + window > now {
            true
        } else {
            self.entries.insert(key, now);
            false
        }
    }

    pub fn set(&mut self, key: &[u8], delay: f64, now: f64) {
        if delay <= 0.0 {
            self.entries.remove(key);
        } else {
            self.entries.insert(key.to_owned(), now + delay);
        }
    }

    pub fn active(&mut self, key: &[u8], now: f64) -> bool {
        let timestamp = *self.entries.get(key).unwrap_or(&0.0);
        if timestamp != 0.0 && timestamp >= now {
            true
        } else {
            self.entries.remove(key);
            false
        }
    }
}

#[pyclass]
#[derive(Default)]
struct RateLimiterCore {
    state: Mutex<RateState>,
}

#[pymethods]
impl RateLimiterCore {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    fn allow(&self, key: &[u8], maximum: usize, window: f64, now: f64) -> PyResult<bool> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .allow(key, maximum, window, now))
    }
    fn remaining(&self, key: &[u8], maximum: usize, window: f64, now: f64) -> PyResult<usize> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .remaining(key, maximum, window, now))
    }
    fn increment(&self, key: &[u8], window: f64, now: f64) -> PyResult<usize> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .increment(key, window, now))
    }
    fn count(&self, key: &[u8], now: f64) -> PyResult<usize> {
        Ok(self.state.lock().map_err(poisoned)?.count(key, now))
    }
    fn reset(&self, key: &[u8]) -> PyResult<()> {
        self.state.lock().map_err(poisoned)?.reset(key);
        Ok(())
    }
    fn snapshot(&self) -> PyResult<Vec<(Vec<u8>, Vec<f64>)>> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .counters
            .iter()
            .map(|(key, values)| (key.clone(), values.iter().copied().collect()))
            .collect())
    }
}

#[pyclass]
#[derive(Default)]
struct DebounceCore {
    state: Mutex<DebounceState>,
}

#[pymethods]
impl DebounceCore {
    #[new]
    fn new() -> Self {
        Self::default()
    }
    fn seen(&self, key: &[u8], window: f64, fingerprint: &[u8], now: f64) -> PyResult<bool> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .seen(key, window, fingerprint, now))
    }
    fn set(&self, key: &[u8], delay: f64, now: f64) -> PyResult<()> {
        self.state.lock().map_err(poisoned)?.set(key, delay, now);
        Ok(())
    }
    fn active(&self, key: &[u8], now: f64) -> PyResult<bool> {
        Ok(self.state.lock().map_err(poisoned)?.active(key, now))
    }
    fn snapshot(&self) -> PyResult<Vec<(Vec<u8>, f64)>> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .entries
            .iter()
            .map(|(key, value)| (key.clone(), *value))
            .collect())
    }
}

fn poisoned<T>(_: std::sync::PoisonError<T>) -> PyErr {
    PyRuntimeError::new_err("Native memory lock poisoned; state cannot be safely reused")
}

#[pyfunction]
fn capabilities() -> (&'static str, u32, &'static str) {
    ("aiogram-sentinel-native", 1, env!("CARGO_PKG_VERSION"))
}

#[pymodule]
fn _aiogram_sentinel_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(capabilities, module)?)?;
    module.add_class::<RateLimiterCore>()?;
    module.add_class::<DebounceCore>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rate_boundaries_and_destructive_window_changes() {
        let mut rate = RateState::default();
        assert!(rate.allow(b"key", 1, 10.0, 100.0));
        assert!(!rate.allow(b"key", 1, 10.0, 110.0));
        assert!(rate.allow(b"key", 1, 10.0, 110.00001));
        // A smaller requested window prunes this key only, just like Python.
        assert_eq!(rate.remaining(b"key", 1, 1.0, 112.0), 1);
        assert_eq!(rate.remaining(b"key", 1, 100.0, 112.0), 1);
    }

    #[test]
    fn quiet_keys_are_not_garbage_collected_for_other_keys() {
        let mut rate = RateState::default();
        rate.allow(b"old", 5, 5.0, 1.0);
        rate.allow(b"other", 5, 5.0, 100.0);
        assert_eq!(rate.remaining(b"old", 5, 1000.0, 100.0), 4);
    }

    #[test]
    fn debounce_zero_and_inclusive_helper_boundaries() {
        let mut state = DebounceState::default();
        assert!(!state.seen(b"key", 10.0, b"fp", 0.0));
        assert!(!state.seen(b"key", 10.0, b"fp", 0.0));
        assert!(!state.seen(b"key", 10.0, b"fp", 1.0));
        assert!(state.seen(b"key", 10.0, b"fp", 10.999));
        assert!(!state.seen(b"key", 10.0, b"fp", 11.0));
        state.set(b"key", 5.0, 10.0);
        assert!(state.active(b"key", 15.0));
        assert!(!state.active(b"key", 15.0001));
    }
}
