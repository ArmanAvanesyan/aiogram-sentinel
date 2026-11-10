# Sentinel 1.3.0 development evidence

This is candidate evidence, not performance qualification or a publication
approval. The authoritative final comparison must run serially on a quiet host
against installed artifacts after source freeze.

Implemented: optional ABI1/native version1.3.0 memory engines, exact-window and
helper parity, pure Python default, no fallback, Python allocation reductions,
no Redis counter shadow. The Redis backend keeps its existing network and error
behavior; only temporary key construction allocations were removed.

## Checks observed locally

- Python3.12 / aiogram3.31 full suite with real Redis7: 378 tests before the final
  malformed-policy regression, 92.33% source coverage. Final count is380.
- Python3.10 / aiogram3.0 installed wheel and companion: 378 tests passed before
  that added regression; final byte-key artifact rerun is recorded in /tmp/sentinel130-min-final-tests.log.
- Redis7 and Redis8 integration suites: 44 passed on each.
- Rust unit tests:3 passed; Clippy all-targets with denied warnings and rustfmt
  passed. Generated Python parity covers2,000 mixed operations and windows, plus
  1,000 competing tasks. No cross-key history garbage collection is introduced.
- Ruff, Black, strict Pyright and strict MkDocs passed.
- Base wheel/sdist and companion macOS x86_64 ABI3 wheel/sdist built; Twine checks
  passed. Native abi3audit strict and individual artifact verifier checks passed.
- Fresh base-only install runs without Redis or native installed.
- Bandit and Python dependency audit found no findings. Cargo-audit0.23.0 also reports no vulnerabilities in the locked Rust graph.

## Timing evidence and limits

`native-development-{baseline,python,rust}.json` use installed packages. Baseline
is published1.2.0. They contain repeated process CPU/batch durations, RSS, metadata
and1,000 individual resolver/throttle/fake-I/O update latencies. Percentiles use
nearest rank. Batch p95 is explicitly distinct from update p95.

These quick runs occurred during other development and predate the final surrogatepass-byte-key compatibility refinement. They cannot qualify the final implementation. In the final quick run,
Rust/Python median CPU ratios were0.75 accepted-hot,0.90 rejected-hot,0.80
accepted-many,0.67 rejected debounce,0.76 accepted debounce,0.91 task concurrency,
and0.84 middleware/fake-I/O. The middleware update p95 ratio was1.13. Therefore
**the <=5% update-p95 gate has not passed**. Do not advertise native performance
or publish the companion based on these runs.

`native-development/pyperf-*.json` retain actual initial pyperf samples; pyperf
warned they were unstable. They predate the final key-hit allocation refinement.
Criterion `new` JSON records actual refined Rust kernel samples. No hosted
wall-time threshold is added to CI.

## Remaining release gates

- Root-level serial matched >=20% representative CPU improvement and <=5%
  middleware update-p95 regression.
- Full7-platform native wheels, installed Python3.10–3.14 matrix and stable-ABI
  verification on CI. Locally only macOS x86_64 was built.
- Native Trusted Publisher registration and independent native-v1.3.0 artifact
  manifest review. No tag, push, GitHub release or PyPI upload performed here.
