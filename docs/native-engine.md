# Optional Rust memory engine (1.3.0 candidate)

The base `aiogram-sentinel` distribution remains a pure Python Hatchling wheel.
Python is the default and needs neither Rust nor the companion. Redis backends
always use Redis atomic operations as their distributed authority; selecting an
engine never adds a local Redis counter cache.

The candidate companion `aiogram-sentinel-native==1.3.0` is built separately with
Maturin and ABI3 for Python 3.10+. It has no dependency on the base distribution.
There is no native extra until publication and performance qualification succeed.

For local evaluation after installing the exact matching companion wheel:

```python
from aiogram_sentinel import SentinelConfig
from aiogram_sentinel.storage.memory import MemoryRateLimiter, MemoryDebounce

config = SentinelConfig(engine="rust")  # memory infrastructure only
limiter = MemoryRateLimiter(engine="rust")
debounce = MemoryDebounce(engine="rust")
```

Explicit Rust selection checks the companion's distribution identity, exact
version and ABI1 capabilities before creating an engine. Missing wheels raise
`NativeEngineUnavailable`; mismatches raise `NativeEngineIncompatible`. Both are
configuration errors. Capability fields require exact tuple/string/integer
types (a boolean is not ABI1), and both complete kernel interfaces are checked
using fresh empty instances before either backend is exposed. This check never
calls a state-mutating operation. A kernel error propagates; no request is replayed against
Python after a native mutation. Do not catch the error and retry with a fresh
engine: that would discard the limiting history.

Both engines use one process's monotonic clock and hold no durable state. Native
calls hold the GIL and a Rust mutex, with no asynchronous I/O or Python callback.
They are atomic without an await; this does not claim parallel CPU throughput.
Python retains its task lock. Separate instances never share counters. Choose
Redis for multiple processes or replicas.

The engines preserve the existing memory behavior: rate-window cutoff is strict
(`< now-window`); duplicate debounce expiration is exclusive, while the direct
`is_debounced` helper includes its deadline. Rejected debounce calls do not extend
the window. Requests with a smaller window destructively discard older entries,
just as before. Other keys are never swept in a way that loses history visible
to a future larger window. This intentionally retains quiet keys; applications
requiring bounded persistent storage should use Redis. Backend keys and
fingerprints follow the public typed contract (`str`), including unpaired
surrogates, preserved through a UTF-8 surrogatepass byte boundary.

## Verification and performance gate

`tests/unit/test_native.py` compares seeded sequences of all public operations,
window changes, keys and exact times against the Python reference. Rust unit
tests also exercise boundaries and quiet-key retention. Native CI builds seven
platform wheels; the separate publisher verifies exact assets and hashes rather
than rebuilding them. Base publishing accepts only base assets.

Run `benchmarks/run.py --engine python|rust --output PATH [--quick]` using an
installed package. The same script supports published 1.2.0, which has no engine
keyword. `benchmarks/pyperf_memory.py` records calibrated pyperf samples; set
`SENTINEL_ENGINE=rust` for native. `cargo bench --manifest-path native/Cargo.toml`
records Criterion kernels. Neither script injects the source tree into imports.

Development results are not release qualification. Root-level serial comparison
must establish at least 20% process CPU benefit in a representative kernel and
no more than 5% end-to-end p95 regression. The native release remains blocked
until that gate and the complete installed platform artifact checks pass.
