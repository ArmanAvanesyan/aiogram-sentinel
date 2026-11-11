# Idle 0.3 and optional navigation integration state growth

All workloads use the final frozen installed Idle wheel SHA256 `1992eb01efa73b89f05bfe6b19c078a899ec79450f7e569fcfac2acd2d0ef182`, independently verified from `/tmp/idle-030-release-dist/aiogram_idle-0.3.0-py3-none-any.whl`. Runtime final head provided by parent: `870bee3`. Peer Nav wheel is `f14220d827755e92547bb9fe37880bc8178c32c1b600f44a15fd6b756ee94ce6`. Environment `/tmp/aiogram-idle-030-qualification` was left unchanged. JSON contains installed artifact paths, versions, Python and Redis versions, exact configs, driver/helper hashes and provenance.

These are **Python-engine** runs, not native qualification. Native release gates remained withheld by the parent. Other parent tests may contend for CPU; deterministic state growth is primary and timings are exploratory. Tracing is disabled. No Telegram operations occur.

Idle storage activation follows its public staged contract:1→2→3, with stable IDs and expected versions on each call, only inside the run's disposable namespace. The first harness attempt incorrectly requested direct1→3 and was stopped before any workload; that setup diagnostic is archived separately and is not a candidate defect. Regression tests now preserve staged Idle activation and unchanged direct Nav activation.

Default fixtures preserve receipt256 capacities and checkpoints1/10/16. Stress fixtures explicitly set receipt limits10000 and checkpoints50/500/5000; they do not claim protected defaults were removed. All fixtures use a16-byte parameter value. Nav historylimit20 remains bounded. Standalone Idle uses an immutable8-hour external session and repeated exempt activity activation. Combined uses library-owned sessions and alternating two tracked screens, with optional integration as the sole link between independent packages.

<!-- TABLE START -->

| Fixture | Operations | Wall seconds | CPU seconds | Client calls | Computed request bytes | Hot bytes | Cold receipt count | Total string bytes | History |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| combined-memory-default | 1 | 0.017 | 0.015 | 0 | 0 | n/a | n/a | n/a | 0 |
| combined-memory-default | 10 | 0.111 | 0.108 | 0 | 0 | n/a | n/a | n/a | 9 |
| combined-memory-default | 16 | 0.195 | 0.192 | 0 | 0 | n/a | n/a | n/a | 15 |
| combined-memory-stress | 50 | 0.783 | 0.781 | 0 | 0 | n/a | n/a | n/a | 20 |
| combined-memory-stress | 500 | 8.716 | 8.700 | 0 | 0 | n/a | n/a | n/a | 20 |
| combined-memory-stress | 5000 | 88.270 | 88.103 | 0 | 0 | n/a | n/a | n/a | 20 |
| combined-redis-default | 1 | 0.047 | 0.033 | 17 | 33,001 | 3727 | 1 | 7261 | 0 |
| combined-redis-default | 10 | 0.608 | 0.466 | 170 | 601,656 | 5478 | 10 | 40340 | 9 |
| combined-redis-default | 16 | 0.994 | 0.771 | 272 | 1,054,633 | 6588 | 16 | 67719 | 15 |
| combined-redis-stress | 50 | 3.308 | 2.608 | 850 | 4,054,156 | 7510 | 50 | 246588 | 20 |
| combined-redis-stress | 500 | 34.450 | 27.485 | 8500 | 44,070,919 | 7519 | 500 | 2621345 | 20 |
| combined-redis-stress | 5000 | 349.894 | 278.320 | 85000 | 444,551,152 | 7524 | 5000 | 26413625 | 20 |
| idle-activate-external-memory-default | 1 | 0.003 | 0.003 | 0 | 0 | n/a | n/a | n/a | 0 |
| idle-activate-external-memory-default | 10 | 0.008 | 0.007 | 0 | 0 | n/a | n/a | n/a | 0 |
| idle-activate-external-memory-default | 16 | 0.011 | 0.010 | 0 | 0 | n/a | n/a | n/a | 0 |
| idle-activate-external-memory-stress | 50 | 0.019 | 0.018 | 0 | 0 | n/a | n/a | n/a | 0 |
| idle-activate-external-memory-stress | 500 | 0.171 | 0.165 | 0 | 0 | n/a | n/a | n/a | 0 |
| idle-activate-external-memory-stress | 5000 | 3.871 | 3.805 | 0 | 0 | n/a | n/a | n/a | 0 |
| idle-activate-external-redis-default | 1 | 0.023 | 0.016 | 9 | 10,162 | 1592 | 1 | 3073 | 0 |
| idle-activate-external-redis-default | 10 | 0.232 | 0.165 | 90 | 116,067 | 1597 | 10 | 10432 | 0 |
| idle-activate-external-redis-default | 16 | 0.368 | 0.263 | 144 | 186,699 | 1597 | 16 | 15340 | 0 |
| idle-activate-external-redis-stress | 50 | 1.125 | 0.805 | 450 | 586,659 | 1595 | 50 | 43092 | 0 |
| idle-activate-external-redis-stress | 500 | 11.214 | 8.039 | 4500 | 5,883,315 | 1596 | 500 | 411044 | 0 |
| idle-activate-external-redis-stress | 5000 | 113.479 | 81.091 | 45000 | 58,872,531 | 1597 | 5000 | 4095088 | 0 |

<!-- TABLE END -->

Hot bytes count exact Redis record keys; cold receipt count excludes indexes. Total string bytes and Redis memory include all keys in the disposable own prefix. Command calls mean execute_command invocations, not TCP round trips; Lua internal commands, inspection, replies, protocol retries and TLS are excluded. Computed request bytes use RESP2 framing. Public snapshot/history metrics use public contracts. Redis state inspection is excluded from CPU/wall workload totals and command counters, then all own-prefix keys are cleaned.


All eight primary fixtures completed. Standalone external Idle Redis has exactly16 retained operation rows after16 activations, rather than the baseline two receipts per activation. Its hot record remains1597 bytes at16 and5000 operations. Combined Redis hot state grows7519→7524 bytes from500→5000 tracks, with history fixed20 and cold rows500→5000. Thus old replay evidence remains separately retained while current state remains bounded.

At16 operations, standalone Idle Redis uses144 client calls /186699 computed request bytes versus baseline384 /689147. Combined Redis uses272 calls /1054633 computed request bytes versus baseline1120 /93375695. Combined Redis5000 has85000 client calls,444551152 computed request bytes,26413625 total string payload bytes and36152104 total Redis memory bytes. Linear work is visible in the500→5000 checkpoints; CPU278.320s is exploratory, not a release/native gate. Combined memory5000 uses88.103s CPU versus standalone Idle3.805s and earlier standalone Nav2.963s; optional integration still has a material constant per-transition validation/serialization cost, although historical accumulation no longer produces quadratic hot-state growth.


Default-capacity admission tests are separate from raised-cap stress. All four profiles accepted256 operations, then rejected operation257 with `Overloaded`. Redis retained256 cold receipt rows at the256 checkpoint; existing evidence was not evicted. No short-retention experiment was added because the existing CLI intentionally exposes no TTL override.

| Boundary fixture | Last accepted | Rejected operation | Error | Cold rows at256 |
| --- | ---: | ---: | --- | ---: |
| combined-memory-default-cap | 256 | 257 | Overloaded | n/a |
| combined-redis-default-cap | 256 | 257 | Overloaded | 256 |
| idle-activate-external-memory-default-cap | 256 | 257 | Overloaded | n/a |
| idle-activate-external-redis-default-cap | 256 | 257 | Overloaded | 256 |
