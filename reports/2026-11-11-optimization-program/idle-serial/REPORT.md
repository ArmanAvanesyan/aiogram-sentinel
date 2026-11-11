# Idle 0.3.0 verification

PR:https://github.com/ArmanAvanesyan/aiogram-idle/pull/3 merged as04a753a.
Version0.3.0 is published (publish42943214622). Exact PyPI wheel/sdist hashes
match; fresh index-only standalone and optional Nav/Redis installs pass, including
an atomic published-wheel memory navigation/activity update. Rust
source and functional tests are complete; its companion package/tag/extra are
withheld because the measured performance gate failed.

## Prespecified matched profiles

PythonA,RustA,RustB,PythonB ran serially while other task agents paused CPU-heavy
work. Primary CPU:standalone memory-activate-touch/50,10 independent batches
of500 operations, fixed draft and immutable external authority, nine successful
touches per activation. Required tail cases:standalone Redis, real protected
Dispatcher unchanged updates and combined Redis tracking,500 individual latencies
per run. Queue claiming is measured separately; loop lag is untimed diagnostics.

Both exact Nav peer artifacts are fixed across engine profiles. Provenance includes
base/native/peer wheel hashes, the complete frozen driver/helper digest and unique
run IDs. Local wheel files are matched against installed archive members; actual
execution uses the same isolated imports as the provenance probe.

| Metric | Rust / optimized Python |
| --- | ---: |
| Representative standalone CPU | 1.0663 |
| Standalone Redis p95 | 1.0013 |
| Combined Dispatcher unchanged p95 | 0.9876 |
| Combined Redis tracked p95 | 1.0095 |

CPU is6.6% slower and fails the required20% benefit. Some memory-tail ratios also
regress, but repeat spread over10% prevents precise tail claims. Redis tails are
near parity. No native publication or production speedup is qualified.

## Storage growth and finite capacity

Independent fixtures use the public APIs, final-growth wheel1992, fixed input size
and20-item history. See ../../optimization/state-growth/candidate-idle-030/.

At5000 operations, standalone Idle hot state is1597B and combined hot state7524B;
each retains5000 separate compact cold receipts. Combined Redis500→5000 hot bytes
are7519→7524, calls8500→85000 and cold evidence grows linearly. No entire historical
Nav ledger is copied into generic Idle snapshots. At16 combined transitions,
client calls are272 versus1120 in published0.2; computed request RESP bytes are
1,054,633 versus93,375,695. These are client calls/request bytes, not Lua-internal
commands or total TCP traffic.

Warm library budgets:4 Redis calls for unchanged Dispatcher updates and17 for
combined tracked adoption. Application authority I/O, application FSM storage,
external rendering, bootstrap, contention and inspection are itemized separately.

Stress fixtures explicitly use10000 receipt slots. All four default-capacity
profiles accept256 actions and reject257 with Overloaded; promised results are
not evicted. Short replay-window behavior is tested separately by the library and
admission diagnostics. Operators must size the replay window/capacity for admitted
traffic. Arbitrary string operation IDs do not provide permanent deduplication
beyond retained evidence; unknown business effects are not automatically repeated.

Timings in growth fixtures are exploratory under concurrent tests. Combined memory
still has substantially higher constant overhead than standalone libraries;
canonical memory commits copy bounded retained metadata. No universal O(1) memory
CPU or production latency claim is made.

## Final artifacts and audit

Final wheel SHA256:
33f1809f8545644982112a7dc596a3463c0df750e36d86fce18acc9e3bb4c90e.
Final sdist SHA256:
f32c39a66c2fe4c705d5b3a9fe36b848e6e3c5f031054e49be6784943b132d7b.
Both contain the same91 runtime files as the reviewed checkout and install
standalone without Nav/Redis/native. Twine passed. SHA256SUMS digest:
06a242636dc2fd8f29ad955d3deb6407075c0e42527a4414a5f307edcc99324f.

Native candidate wheel e175c4b9f03565f88e14456b82b45146fd930a4c73be245ee1995c606ac74b0a
and fixed Nav base f14220d827755e92547bb9fe37880bc8178c32c1b600f44a15fd6b756ee94ce6 /
native972468d8934db2278565a835b899b52231fd1c778545d5af7e5b3134235ba5ae were used.
The paired native benchmark uses earlier Idlea6f5; growth uses1992. Final changes
are README, offline migration aggregate-budget prevalidation and explicit typed
guards replacing assertions. artifact-delta.json lists every changed wheel member.
The failed native decision is retained conservatively; no positive qualification
for different final bytes is claimed.

Verification includes729 source cases/85.42% complete optional-integration
coverage, four format-three profiles486/486/143/143, installed minimum/current
profiles470 each and final targeted regressions. Independent audit37 cases
passed; its last memory migration ordering issue is fixed with3 regressions.
The final CI42941136921, native platform42941136933 and mixed-engine42941136976
all passed before merge. The actual downloaded native wheels run on regular
CPython3.10–3.14 across seven platform targets; sdists rebuild and pass tests.
Bandit and dependency audits report zero findings; typing/lint/docs pass.

## Rollout

No application deployment or live data migration was performed. Installing0.3 does
not upgrade existing Redis layouts. Back up and drain old writers, then assess and
explicitly activate supported format progression before migrating components.
Memory is single-process/non-durable; Redis durability depends on deployment.
See the package's docs/migration-0.3.md for staged recovery, immutable backup
retention/cleanup and host authority/expiry rules.
