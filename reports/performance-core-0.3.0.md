# 0.3.0 implementation and verification

Local candidate implementation: `1e91747946f57b10e55aaaba1d31dcc416ea2de3`.
This is source verification, not publication or performance qualification.

## Delivered

- Optional explicitly selected deterministic Rust core; Python remains the default.
  The companion has no base dependency; missing/skewed capabilities fail before I/O.
- Cached structural codecs, linear graph validation, bounded expiry pruning and
  one-operation adoption of an application-owned render.
- Opt-in format 3 hot state and physically separate operation receipts with Redis
  server-time terminal TTL, protected unknown work, bounded selected reads,
  scoped view ownership and reverse-index cardinality evidence.
- Drained-writer activation, restart-safe lazy conversion preserving absolute
  deadlines, and bounded explicit eager migration pages.
- Public canonical-ledger contracts for the optional Idle host. The host commits
  Nav operation/state and Idle activity/deadline together; it does not duplicate
  retained historical Nav snapshots. Pure host generation binding precedes view
  ownership checks; previously promised deadlines cannot be extended.

## Verification completed locally

- Strict Pyright: zero errors. Ruff and `git diff --check`: clean.
- MkDocs strict build passed; Bandit medium/high gate passed.
- Real Redis 7 full suite: 449 passed before the final three added assertions.
- Real Redis 8 full suite: 452 passed, 84.55% branch-aware coverage.
- Existing 50 concurrent-worker/crash/transport/control/FSM cases forced to format 3:
  Python 50 passed; Rust 50 passed.
- Scoped retained-view reuse tested across memory/Redis and Python/Rust.
- Wrong-type targets and witness, missing index/owner/witness, malformed witness,
  malformed hot-session header, expired generation and failed-adoption rollback
  regressions passed.
- Minimum base wheel (Python 3.10 / aiogram 3.22): 327 passed, 125 optional tests
  skipped, with Redis/Idle/native absent; installed version and `py.typed` checked.
- Current base source install (Python 3.12 / aiogram 3.31): 327 passed, 125
  optional tests skipped, with Redis/Idle/native absent.
- Native clean extracted-sdist rebuild: 51 parity/property tests passed. Native
  unit/Clippy/Rustfmt and local Python 3.10/3.12/3.14 parity passed separately.

## Candidate artifacts

Base wheel SHA256:
`f14220d827755e92547bb9fe37880bc8178c32c1b600f44a15fd6b756ee94ce6`

Base source SHA256:
`7001524a1a4979ca1ee3d3c79438f13ce8c598b8f2e1a17828d6d53769d75c89`

Native local macOS x86_64 ABI3 wheel SHA256:
`972468d8934db2278565a835b899b52231fd1c778545d5af7e5b3134235ba5ae`

Native source SHA256:
`5b84c8ab2d5d9e2e03deb23c78a0dfee88fb466e625a97323db59b2ec07626fb`

The base artifacts contain no required Redis, Idle or native dependency. The
base source excludes native build output. No artifacts were published by this
implementation stream.

## Remaining release gates

Independent installed-artifact benchmark qualification and remote platform CI
remain required. Every benchmark JSON sets `qualification=false`; only the
independent repeated serial comparison can qualify native publication. Native
publication and a `[native]` extra remain withheld unless its measured benefit
and realistic p95 gates pass. Existing microbenchmarks are reported honestly in
`native/BENCHMARKS.md`; a published-old-version improvement does not establish a
native-over-optimized-Python improvement.

## Independent native qualification verdict

The repeated serial installed-artifact qualification failed the required native
benefit gate. On the preselected `memory-track/50` workload, Rust/Python process
CPU was 1.2173843 (Rust 21.7% slower); individual-update p95 was 1.224. Whole Redis
protected-handler p95 ratios were 1.0014 for no-op and 1.0121 for track. Neither
near-parity Redis latency nor a published-baseline improvement satisfies the
required 20% native CPU benefit. Native PyPI publication, a native release tag and
an advertised `[native]` extra are therefore withheld. Functional Rust source and
platform/parity CI remain available for future optimization.

The optimized Python whole-handler profile used three library Redis round trips
for no-op and eight for tracked navigation, below the five/twenty budgets. At age
50 the tracked update transferred approximately 16.8 KB sent and 21.1 KB received.
These measurements include client traffic separately from Lua internal commands.
Independent evidence is maintained in Kit's `nav-serial/native-gate.json`; it used
the exact base/native artifact hashes above with repeated serial runs. No native
publication is authorized by this result.
