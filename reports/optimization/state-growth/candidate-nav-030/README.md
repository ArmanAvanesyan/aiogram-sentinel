# Nav 0.3 Python installed-artifact state growth

The parent-provided frozen candidate environment is `/tmp/aiogram-nav-030-qualification`; the installed base wheel has SHA256 `f14220d827755e92547bb9fe37880bc8178c32c1b600f44a15fd6b756ee94ce6`. All runs explicitly use **Python**, storage format 3, installed noneditable imports and no Telegram. Native support is not qualified by these runs. The artifact environment was not modified.

The default-capacity comparison preserves 256 receipts and checkpoints 1/10/16. The separate stress workload explicitly permits 10,000 receipts and checkpoints 50/500/5000; this does not imply default replay-protected capacity was removed. History limit20 and 16-byte parameter value match baseline. Each run gets its own disposable Redis namespace, inspected after checkpoint, then removed.

Timing is exploratory: other parent test work can contend for CPU. `tracemalloc` is disabled. JSON records exact driver/helper hashes, library and Redis versions, artifact paths, configuration, cumulative command accounting, RSS and loop-lag measurements. Deterministic state growth is the primary result; these are not native qualification runs.

| Fixture | Operations | Wall seconds | CPU seconds | Client calls | Computed request bytes | Hot bytes | Cold receipt count | Total string bytes | History size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nav-memory-default | 1 | 0.002 | 0.002 | 0 | 0 | n/a | n/a | n/a | 0 |
| nav-memory-default | 10 | 0.008 | 0.008 | 0 | 0 | n/a | n/a | n/a | 9 |
| nav-memory-default | 16 | 0.013 | 0.013 | 0 | 0 | n/a | n/a | n/a | 15 |
| nav-memory-stress | 50 | 0.034 | 0.033 | 0 | 0 | n/a | n/a | n/a | 20 |
| nav-memory-stress | 500 | 0.309 | 0.301 | 0 | 0 | n/a | n/a | n/a | 20 |
| nav-memory-stress | 5000 | 3.040 | 2.963 | 0 | 0 | n/a | n/a | n/a | 20 |
| nav-redis-default | 1 | 0.012 | 0.008 | 6 | 12,545 | 1155 | 1 | 4412 | 0 |
| nav-redis-default | 10 | 0.164 | 0.111 | 69 | 169,601 | 2225 | 10 | 32828 | 9 |
| nav-redis-default | 16 | 0.286 | 0.199 | 111 | 292,418 | 2936 | 16 | 57149 | 15 |
| nav-redis-stress | 50 | 1.154 | 0.828 | 349 | 1,090,345 | 3529 | 50 | 220576 | 20 |
| nav-redis-stress | 500 | 12.419 | 9.204 | 3499 | 11,719,465 | 3533 | 500 | 2394990 | 20 |
| nav-redis-stress | 5000 | 135.163 | 101.313 | 34999 | 118,130,987 | 3537 | 5000 | 24179504 | 20 |

Redis hot bytes count the exact `record:<id>` key. Cold receipts count standalone operation rows; metadata/index keys are excluded from that count but included in total-prefix key/memory measurements. Total string bytes include all own-prefix string keys; the JSON also reports total Redis `MEMORY USAGE` across strings and indexes. Historical results are retained rather than evicted; expected total cold storage grows linearly during this replay window. Public navigation snapshots contain at most20 history entries.

At16 operations, the candidate Redis hot record is2,936 bytes, versus the baseline0.2 monolithic record51,741 bytes. Candidate111 client-command invocations and292,418 computed RESP request bytes compare with baseline247 and3,195,297. CPU times0.199s versus6.714s are exploratory observations only. Candidate total string state57,149 bytes exceeds baseline51,997 bytes because separating replay evidence incurs per-row serialization overhead while bounding the hot path.

Command calls mean `Redis.execute_command` invocations, not TCP round trips; Lua internal work is not counted as client commands. Computed RESP2 request bytes exclude replies, protocol retries and TLS. Checkpoint state inspection and output writing are excluded from timing and command accounting.

At500 versus5000 stress operations, Redis hot state grows only3,533→3,537 bytes while retained cold receipts grow500→5000 and total string payload2,394,990→24,179,504 bytes. Current history remains20. Calls3,499→34,999 and cumulative request bytes11,719,465→118,130,987 show roughly linear hot-path work; historical evidence remains separately retained. No protected receipt was evicted to manufacture bounded storage. CPU9.204→101.313 seconds is exploratory under parent workloads. Memory5000 completes with2.963 CPU seconds and20 history entries. All four candidate fixtures completed successfully.
