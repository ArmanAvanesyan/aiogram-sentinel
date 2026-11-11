# Nav 0.3.0 candidate verification

PR:https://github.com/ArmanAvanesyan/aiogram-nav/pull/2 merged as a5a0696.
Version0.3.0 is published with matching PyPI hashes and a fresh index-only
standalone install verified (publish42936943326). Python stays default. The Rust companion is implemented and
functionally verified, but its distribution/tag/extra are withheld.

## Prespecified native gate

Order:PythonA,RustA,RustB,PythonB, serially on the host in the program machine
manifest. Other task agents paused tests and compilation during this window.
Each run uses the exact installed base wheel and an isolated import bootstrap;
Rust profiles use the matching exact native wheel. The controller validates local
wheel files against every installed archive member before recording their digest.
Drivers/helpers were frozen and identical across all four runs.

CPU gate:memory-track/50,10 independent batches of1000 operations. Tail gates:
protected Dispatcher unchanged/tracked Redis updates at age50,1000 individual
updates per workload. Memory measurements also retain10000 individual latencies.

| Metric | Rust / optimized Python |
| --- | ---: |
| Representative memory CPU | 1.2174 |
| Memory operation p95 | 1.2243 |
| Redis unchanged update p95 | 1.0014 |
| Redis tracked update p95 | 1.0121 |

Representative CPU is21.7% slower, failing the required20% benefit; memory p95
also regresses. Repetition spread did not trigger the instability gate. Redis
latency is near parity, not a demonstrated speedup. See native-gate.json, raw
measurements and run manifests; no native release is authorized by this evidence.

## Python storage and call budgets

The installed whole-Dispatcher profile used3 Redis round trips for unchanged
updates and8 for tracked adoption. At age50, tracked request/response RESP p95 was
about16.9KB/21.1KB. These counts include library coordination; application-owned
FSM storage, external authority I/O, startup, contention and external rendering are
separate. Cold namespace initialization is recorded independently. Redis internal
Lua commands are not substituted for network round trips.

Independent public-API growth fixtures are in
../../optimization/state-growth/candidate-nav-030/. With an explicit10000-slot
stress capacity and fixed20-item history, at500→5000 operations:

- Hot record3533→3537bytes.
- Canonical receipt rows500→5000; cold payload2.391→24.175MB.
- Client calls3499→34999; request bytes11.719→118.131MB.

Current-state size is bounded and retained evidence grows linearly. Default
capacity remains256; the stress override does not promise unlimited traffic.
Configure the terminal replay window and capacity for the admitted rate. Unexpired
promised results and unresolved effects are not evicted; expired terminal evidence
is reclaimable. These growth-run timings were collected under concurrent tests
and remain exploratory.

Separate quick registry-chain probes (50/500/5000 nodes) illustrate the linear
Python index replacing repeated ancestry walks. They are startup diagnostics on
an intentionally deep tree, not a general production speedup or native gate.

## Exact artifacts and functional checks

Final base wheel SHA256:
f14220d827755e92547bb9fe37880bc8178c32c1b600f44a15fd6b756ee94ce6.
Final sdist SHA256:
8204f3d72fee86b483685f01599f9f86605f516ef31515fc77b4e89cc1dab649.
The rebuilt final wheel is byte-identical to the measured wheel. All60 source
files in the final sdist match the checkout and measured wheel. Fresh final sdist
base-only installation passed typing/version/memory/optional-dependency probes.

Native wheel SHA256:
972468d8934db2278565a835b899b52231fd1c778545d5af7e5b3134235ba5ae.
Native sdist SHA256:
5b84c8ab2d5d9e2e03deb23c78a0dfee88fb466e625a97323db59b2ec07626fb.

Runtime verification:452 real-Redis tests,84.55% coverage; minimum wheel
Python3.10/aiogram3.22/Redis client5 on server7 and current extracted-sdist
Python3.12/aiogram3.31/client7 on server8 passed452 tests each. Base-only wheel and
sdist profiles without optional dependencies passed327 tests each. Existing
format-three fault/FSM/control corpus50 tests passed per engine; independent
ledger/adoption/migration audit38 tests passed. Native extracted-sdist rebuild
passed51 tests and standalone Python3.10 import without Base/Idle/Redis passed.
Base CI42935475611 and actual platform artifact CI42935475662 both passed
before merge/publication. The final release includes SHA256SUMS and VERIFICATION.md.

## Rollout boundary

Installing the wheel does not migrate existing Redis data. New namespaces can
explicitly select storage_format=3; existing namespaces require backup, draining
old writers, assessment and explicit activation/migration. See the package's
performance/storage documentation. No application configuration, production
namespace or deployment was changed by this program.
