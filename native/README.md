# aiogram-idle-native

Optional deterministic Rust acceleration for aiogram-idle 0.3.0. Maturin builds a
CPython abi3-py310 wheel. This distribution has no dependency on the base library.
The base defaults to Python; explicitly selecting Rust requires this exact 0.3.0
companion with API_VERSION 1 before mutation, with no fallback after a failure.

Rust owns the lifecycle transition table, activity/session/claim guard decisions,
exact supplied-byte SHA256, receipt duplicate/conflict/capacity decisions, and an
authoritative generation-checked deadline heap with scheduling, claims, renewal,
conditional release/completion, compaction and bounded reconciliation. Python owns
model construction, clocks, random tokens, locks, I/O and all application effects.
Canonical fingerprint strings are supplied by Python unchanged, preserving numeric
formatting, Unicode escapes and durable operation identity across engines.

Build `uvx maturin build --release --manifest-path native/Cargo.toml`; test
`cargo test --manifest-path native/Cargo.toml`; benchmark
`cargo bench --manifest-path native/Cargo.toml --bench core`. The native companion
is separately published by native-v* tags, never by the base Python-only workflow.
An sdist install requires Rust/Cargo. Cargo.lock is retained for reproducibility.
Native microbenchmarks do not establish end-to-end Redis/Telegram speedups. The
performance gate is qualified separately on a labelled host and may reject use of
the optional engine when the >=20% CPU / <=5% real-p95-regression gates are not met.

The low-level extension uses canonical hexadecimal strings for revisions/generations
and receipt counters, backed by Rust BigUint rather than lossy machine integers.
The base library's typed adapter keeps ordinary Python integer/model APIs. Opaque
identities crossing the extension boundary are ASCII JSON strings, preserving
all Python Unicode codepoints, including isolated surrogates accepted by legacy
identity models; they are compared, never interpreted by Rust.
