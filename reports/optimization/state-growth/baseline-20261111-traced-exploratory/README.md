# Published 0.2 traced exploratory profile

**Do not use these timings for CPU/native performance comparisons.** Tracing Python allocations imposes uneven overhead and cannot observe native allocations.

Exploratory measurements of **installed artifacts**, with no real Telegram traffic. These are traced workload measurements, not native-engine qualification or a latency SLA. The JSON files retain exact interpreter, distribution, Redis, configuration, driver hash and fixture metadata.

All workloads alternate two screens or repeatedly activate one exempt idle activity, use a 20-entry history limit and a 16-byte parameter value, and stop at 16 operations for this initial baseline. Default receipt capacities are preserved. Idle uses an immutable external session and explicitly activates storage format 2; combined and standalone navigation use library-owned sessions and their default format. No expiry or garbage collection is forced.

| Fixture | Outcome | Operations | Wall seconds | CPU seconds | Client command calls | Computed request bytes | Redis record bytes | Traced peak bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| combined-memory | completed | 16 | 27.724 | 27.695 | 0 | 0 | n/a | 3,594,409 |
| combined-redis | completed | 16 | 86.368 | 83.559 | 1125 | 93,426,595 | 2159461 | 12,525,263 |
| idle-activate-external-memory | completed | 16 | 0.022 | 0.021 | 0 | 0 | n/a | 242,604 |
| idle-activate-external-redis | completed | 16 | 3.116 | 2.784 | 384 | 689,345 | 15549 | 994,450 |
| nav-memory | completed | 16 | 0.041 | 0.041 | 0 | 0 | n/a | 146,528 |
| nav-redis | completed | 16 | 36.716 | 36.357 | 253 | 3,201,578 | 51741 | 2,139,976 |

Command counts are `Redis.execute_command` invocations, not TCP round trips. Pipeline execute calls are separate; Lua internal operations are excluded. Computed RESP2 request bytes exclude replies, connection setup, protocol retries, TLS and compression. State-size inspection and report writing are outside the timed sections and command counters. Lazy initialization during the first workload operation is included.

`tracemalloc` is enabled and materially amplifies Python allocation costs, especially combined snapshot copying. Memory rows report traced Python allocations and public snapshot bytes rather than a private receipt-store estimate. Redis rows inspect only their generated disposable prefix, then delete it. Event-loop lag is sampled every 5 ms; short workloads can have very few samples.

The driver rejects editable/source imports, and was invoked with `python -I`. Example:

```sh
/tmp/aiogram-optimization-published-baseline/bin/python -I tools/optimization/benchmark_state_growth.py --trace-memory --mode combined --screens 1 10 16 --output reports/optimization/state-growth/baseline-20261111/combined-memory.json
```

Add `--redis-url redis://127.0.0.1:16650/0` for isolated Redis. External idle uses `--external-sessions`; `--idle-operation touch` selects touch after initial activation. New-artifact scalability experiments may explicitly raise `--receipt-limit`; that is a separate workload and does not claim removal of the protected default capacity. Format 3 activation requires explicit `--storage-format3` and affects only the run's unique disposable namespace. Rust selection is explicit and fails when unsupported.
