# aiogram-nav-native

Optional deterministic Rust acceleration for aiogram-nav 0.3.1, built with
Maturin and CPython's abi3-py310 stable ABI. The distribution has no dependency
on the base library. Install it explicitly and select `engine="rust"` in the base
library; missing or incompatible native APIs must fail before state mutation.

Rust owns graph validation/cached targets, strict JSON parsing, bounded history
and scalar transition calculations, token provenance comparison, and exact-byte
SHA256. Typed Python model construction, application validators, I/O, locking,
clocks, random generations and presenter/business effects stay in Python.
Canonical JSON text for fingerprints is supplied by Python, preserving Unicode,
float formatting and arbitrary integer receipt identities across engines.

Build: `uvx maturin build --release --manifest-path native/Cargo.toml`.
Run Rust tests: `cargo test --manifest-path native/Cargo.toml`.
Run Criterion: `cargo bench --manifest-path native/Cargo.toml --bench core`.
Install the wheel in a clean environment, then run `pytest -c native/pytest.ini native/tests`.

Release the companion using its own `native-v0.3.1` tag and an explicitly scoped
native publishing workflow. It must not be published by the base Python-only
workflow. Wheels require platform CI and per-platform smoke tests; an sdist
requires Cargo/Rust when installed. Cargo.lock is committed for reproducibility.

The importable extension is `aiogram_nav_native._aiogram_nav_native`; the public
`aiogram_nav_native` package re-exports its API. Both expose `API_VERSION == 1`
and `ENGINE_VERSION == "0.3.1"` for compatibility checks before mutation.
`strict_loads` preserves object insertion order, arbitrary Python integers,
finite floats and negative zero. Parsing rejects duplicate decoded object keys,
non-finite floating values and unpaired Unicode surrogates. `max_depth` counts raw
JSON containers; typed codec callers use 512 so their own 64-level tagged-model
policy remains authoritative. A configured raw depth above 512 is rejected.

`transition_history` receives plain JSON arrays and an optional current entry;
`push_current` must reflect the already-validated node/parameter change.
`transition_state` takes the old state's scalar fields as JSON and returns the
new revision/time fields. Its timestamp and `token_matches`' actor/time arguments
are decimal strings, preserving arbitrary Python integer domains without an i64
conversion. The library wrapper retains model and session validation.

Native presence alone is not evidence of a speedup. Benchmark the selected engine
against the optimized Python engine on the intended workload before choosing it.

Publication is gated on the approved end-to-end benchmark threshold against the
optimized Python engine. Primitive SHA/JSON microbenchmarks are diagnostic only:
a native boundary can add conversion overhead even when the underlying Rust
algorithm is fast. No base dependency extra or native release should be enabled
from correctness tests alone.
