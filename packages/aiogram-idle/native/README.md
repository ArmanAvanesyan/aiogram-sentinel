# aiogram-idle-native

Optional deterministic Rust implementation for aiogram-idle 0.3.1. Maturin builds a
CPython abi3-py310 wheel. This distribution has no dependency on the base library.
The base defaults to Python; explicitly selecting Rust requires this exact 0.3.1
companion with API_VERSION 1 before mutation, with no fallback after a failure.

**Release status: source-only, not published or tagged for 0.3.1.** The serial
representative CPU gate failed: Rust used about 6.6% more process CPU than Python
on `memory-activate-touch/50`, instead of the required 20% reduction. Redis tails
were near parity, and noisy repeated tail measurements do not establish a benefit.
Keep the default Python engine. Native functional/parity CI is retained; it is not
a performance qualification or a promise of a native package release.

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
can be published separately by native-v* tags, never by the base Python-only workflow.
No native tag or PyPI distribution is released for this version.
An sdist install requires Rust/Cargo. Cargo.lock is retained for reproducibility.
Native microbenchmarks do not establish end-to-end Redis/Telegram speedups. The
performance gate is qualified separately on a labelled host and may reject use of
the optional engine when the >=20% CPU / <=5% real-p95-regression gates are not met.

The low-level extension uses canonical hexadecimal strings for revisions/generations
and receipt counters, backed by Rust BigUint rather than lossy machine integers.
The base library's typed adapter keeps ordinary Python integer/model APIs. Opaque
identities crossing the extension boundary are ASCII JSON strings, preserving
low-level opaque Python codepoints; they are compared, never interpreted by Rust.
Public persistent identifiers and JSON parameters reject surrogate code units early,
using the same strict UTF-8 Unicode scalar contract for both engines.
