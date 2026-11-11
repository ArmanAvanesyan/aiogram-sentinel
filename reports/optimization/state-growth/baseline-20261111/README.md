# Published 0.2 untraced state-growth baseline

Installed, noneditable artifacts: aiogram-nav0.2.0, aiogram-idle0.2.0, aiogram-coordination0.1.0; exact versions and paths are in each JSON metadata block. No real Telegram traffic. These exploratory runs have tracing **disabled**.

All workloads alternate two screens or repeatedly activate one exempt idle activity, use a 20-entry history limit and a 16-byte parameter value, and stop at 16 operations for this initial baseline. Default receipt capacities are preserved. Idle uses an immutable external session and explicitly activates storage format 2; combined and standalone navigation use library-owned sessions and their default format. No expiry or garbage collection is forced.

| Fixture | Outcome | Operations | Wall seconds | CPU seconds | Client command calls | Computed request bytes | Redis record bytes | Process peak RSS bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| combined-memory | completed | 16 | 5.450 | 5.448 | 0 | 0 | n/a | 177,438,720 |
| combined-redis | completed | 16 | 22.353 | 19.502 | 1120 | 93,375,695 | 2158657 | 198,230,016 |
| idle-activate-external-memory | completed | 16 | 0.007 | 0.007 | 0 | 0 | n/a | 171,859,968 |
| idle-activate-external-redis | completed | 16 | 0.877 | 0.610 | 384 | 689,147 | 15543 | 177,434,624 |
| nav-memory | completed | 16 | 0.014 | 0.013 | 0 | 0 | n/a | 171,466,752 |
| nav-redis | completed | 16 | 7.039 | 6.714 | 247 | 3,195,297 | 51741 | 178,589,696 |

Command counts are `Redis.execute_command` invocations, not TCP round trips. Pipeline execute calls are separate; Lua internal operations are excluded. Computed RESP2 request bytes exclude replies, connection setup, protocol retries, TLS and compression. State-size inspection and report writing are outside the timed sections and command counters. Lazy initialization during the first workload operation is included.

`tracemalloc` is disabled. Process peak RSS includes interpreter imports, connection buffers, state inspection and the whole process lifetime; it is not isolated per-operation allocation. Public snapshot bytes do not estimate private receipt-store size. Separate traced exploratory profiles are retained in the sibling directory and cannot gate CPU comparisons. Redis rows inspect only their generated disposable prefix, then delete it. Event-loop lag is sampled every 5 ms; short workloads can have very few samples.

The driver rejects editable/source imports, and was invoked with `python -I`. Example:

```sh
/tmp/aiogram-optimization-published-baseline/bin/python -I tools/optimization/benchmark_state_growth.py --mode combined --screens 1 10 16 --output reports/optimization/state-growth/baseline-20261111/combined-memory.json
```

Add `--redis-url redis://127.0.0.1:16650/0` for isolated Redis. External idle uses `--external-sessions`; `--idle-operation touch` selects touch after initial activation. New-artifact scalability experiments may explicitly raise `--receipt-limit`; that is a separate workload and does not claim removal of the protected default capacity. Format 3 activation requires explicit `--storage-format3` and affects only the run's unique disposable namespace. Rust selection is explicit and fails when unsupported.
