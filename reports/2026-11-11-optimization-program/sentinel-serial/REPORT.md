# Sentinel matched benchmark review

Measured on CPython3.12.13, macOS15.8.1 Intel, same installed dependencies and surrogate-safe native core. Serial order: baseline, Python, Rust, Rust, Python, baseline. Each profile uses50000operations/workload,15measurement batches and5warmups; middleware tails use1000individual updates.

| Workload | Optimized Python / published CPU | Rust / optimized Python CPU |
| --- | ---: | ---: |
| rate_accepted_hot | 1.000 | 0.842 |
| rate_rejected_hot | 0.989 | 0.867 |
| rate_accepted_many | 0.974 | 0.884 |
| debounce_rejected_hot | 1.000 | 0.904 |
| debounce_accepted_many | 1.031 | 0.924 |
| rate_concurrent | 1.019 | 0.955 |
| middleware_fake_io | 0.885 | 1.032 |

Native publication is **withheld**: representative accepted-many rate/debounce gains are below20%. Middleware p95 repeat variation exceeds10%; its apparent tail improvement is not qualified. See native-gate.json and raw run manifests; Lua/server commands are not substituted for network round trips.

The measured native hot core is unchanged by the subsequent ABI-loader hardening; no speed qualification is claimed for the native distribution. The Python middleware path used about11% less CPU in this host/workload; other memory paths were near baseline. No universal latency claim is made.
