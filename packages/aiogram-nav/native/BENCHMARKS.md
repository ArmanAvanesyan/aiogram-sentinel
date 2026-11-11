# Native diagnostic measurements

These measurements are diagnostics from macOS 15.8.1 x86_64, CPython 3.12.13 and
Rust 1.97.1 on 11 November 2026. They are not the end-to-end release gate against
optimized Python. The shared repository benchmark runner owns that comparison.

A fixed JSON document containing 20 nodes, integer revisions, nested parameters,
Armenian text, an emoji, a boolean and negative zero was measured with five
repetitions of 2,000 calls (`timeit`, median time per call). Python used
`json.loads(..., object_pairs_hook=duplicate_rejecting_pairs)`:

| Diagnostic | Python | Native |
| --- | ---: | ---: |
| Strict JSON to Python values | 43.60 µs | 62.85 µs |
| SHA256 of exact canonical text | 5.78 µs | 9.77 µs |

Those boundaries regressed; they do not establish native acceleration. Python's
existing C implementations and conversion costs matter.

A compiled deep-chain registry comparison against the **published 0.2.0** Python
implementation, excluding Python Node construction and pre-serializing the native
input, measured:

| Nodes | Published Python | Native |
| --- | ---: | ---: |
| 50 | 0.312 ms | 0.185 ms |
| 500 | 31.993 ms | 2.159 ms |
| 5,000 | 2,947.487 ms | 19.134 ms |

This mostly demonstrates the old quadratic graph-validation cost. The optimized
Python implementation also removes that cost; the table cannot justify a native
release against it. The actual engine benchmark must include native input
serialization and Python model construction consistently.

Criterion is committed in `benches/core.rs`. A diagnostic run used
`cargo bench --manifest-path native/Cargo.toml --bench core -- --sample-size 10
--measurement-time 1 --warm-up-time 1`; the graph-kernel intervals were
159.95–166.87 µs, 1.8406–1.9370 ms and 20.173–21.453 ms for 50/500/5,000 nodes.
These are Rust-only kernel measurements with no Python boundary. Short samples,
shared-machine load and outliers limit their precision. History-trimming cases
are payload-size stress tests, not high-level retained-receipt workloads.

Native publication and a dependency extra remain blocked until the approved
representative end-to-end gate shows a real benefit without the prohibited p95
regression. Correctness and ABI parity alone do not satisfy that gate.
