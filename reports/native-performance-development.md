# Sentinel 1.3.0 evidence and native release decision

**Native publication is withheld.** The completed serial qualification failed
the required 20% process CPU improvement. The source core remains available for
evaluation, with no native-v tag, native release or `[native]` extra. The optimized
Python base 1.3.0 can ship independently, subject to its normal release checks.

Implemented: optional ABI1/version 1.3.0 memory engines, exact-window and helper
parity, surrogatepass byte keys, Python default, no fallback, allocation
reductions and no Redis counter shadow. Redis network/error behavior remains
unchanged; only temporary key construction allocations were removed.

## Completed serial qualification

The matched ABBA comparison used installed artifacts on macOS 15.8.1 x86_64,
CPython 3.12.13, reporting 16 logical CPUs: two Python runs and two Rust runs,
50,000 operations per batch, 15 measured batch samples per run. It used the final
surrogatepass byte-key hot paths.

| Selected workload | Rust/Python CPU ratio | Measured CPU reduction | Decision |
| --- | ---: | ---: | --- |
| Accepted rate-limit operations, many keys | 0.88350 | 11.65% | below 20% requirement |
| Accepted debounce operations, many keys | 0.92370 | 7.63% | below 20% requirement |

The middleware/fake-I/O update p95 ratio was 0.71225, but the Python repeat spread
exceeded 10%, failing the stability gate. No tail-latency gain is established.
These results apply only to the measured host and workloads; they do not support
universal performance claims.

The constructor ABI hardening validates exact capability types and the complete
kernel interface. It changes neither the measured hot paths nor the native
artifact and does not qualify speed. See the [decision and input hashes](native-serial-gate.json)
and [benchmark explanation](../native/BENCHMARKS.md).

## Functional checks observed locally

- Before constructor ABI hardening: 380 tests passed on Python 3.12 / aiogram
  3.31 with real Redis 7, with 92.34% source coverage. The final byte-key wheel
  and companion also passed all 380 tests on Python 3.10 / aiogram 3.0.
- After ABI hardening: all 30 focused native tests pass on both current and
  minimum installed profiles. The complete current collection contains 395
  tests; this collection count is not a claim of a new full-suite run.
- Redis 7 and Redis 8 integration suites: 44 passed on each.
- Rust unit tests: 3 passed; Clippy all-targets with denied warnings and rustfmt
  passed. Generated parity covers 2,000 mixed operations and window changes,
  1,000 competing tasks, unpaired surrogates, NUL and helper/composite collisions.
- Ruff, Black, strict Pyright, strict MkDocs and workflow actionlint passed.
- Base wheel/sdist and companion macOS x86_64 ABI3 wheel/sdist built; Twine,
  strict abi3audit and individual hardened artifact-verifier checks passed.
- Fresh base-only install works without Redis or native installed.
- Bandit, Python dependency audit and Cargo-audit 0.23.0 found no vulnerabilities.

## Preliminary evidence retained for reproducibility

`native-development-{baseline,python,rust}.json` contains preliminary installed
package samples, including published 1.2.0. Those quick runs occurred during
other development and predate final surrogatepass compatibility changes; they
cannot qualify the final implementation. Batch p95 is explicitly distinct from
individual update p95, using nearest-rank percentiles.

`native-development/pyperf-*.json` retains actual initial samples that pyperf
warned were unstable. Criterion `new` JSON records Rust kernel samples. These
functional/kernel measurements do not override the serial qualification failure.
No noisy hosted wall-time threshold is imposed in CI.

Native wheel CI and any future publisher setup remain separate operational
checks. Passing those checks would not authorize publishing this withheld
companion or advertising a performance gain.
