# Four-library optimization and optional Rust implementation

Approved implementation, 11 November 2026. Delivery is in progress; this document
is a coordination record and does not claim unobserved implementation or releases.

## Fixed decisions

- Optimize Sentinel, Cmds, Nav and Idle and implement Rust deterministic cores in
  all four. Keep aiogram/async I/O/application callbacks/FSM orchestration in Python.
- Python remains the default and supported fallback, selected at construction.
  Explicit Rust selection requires its matching installed companion; no fallback
  after an operation starts. Base distributions remain pure Python/Hatchling.
- Companions live in each repository's native/ Maturin project and have exactly
  the matching base version, with independent core ABI1. They do not depend on
  the base distribution. A future native extra pins the exact companion.
- Target versions: Sentinel1.3.0; Cmds/Nav/Idle0.3.0. First deliver Idle0.2.1
  correctness patch separately. Root coordinates publication; agents commit local
  checkpoints and independent audit precedes pushes/merges/releases.
- Native releases require >=20% lower representative CPU cost and no repeatable
  >5% end-to-end p95 regression. Complete source/benchmarks even if a native
  companion is withheld. Never advertise an extra with an unavailable dependency.
- Regular CPython3.10–3.14: Linux glibc/musl x86_64/ARM64, macOS Intel/ARM64,
  Windowsx86_64. Pure Python stays available elsewhere. Free-threaded native and
  WindowsARM64 are outside the first guaranteed wheel matrix.

## Replay and storage contract

Format3 separates current/pending state from canonical per-operation terminal
results and controls. Combined navigation owns its canonical operation evidence;
Idle must not retain duplicate RuntimeSnapshot ledgers per projection write.
State, receipts and activity/deadline changes remain one fenced transaction.

Replay retention is finite, defaults to the existing recovery-retention setting,
and starts at authoritative terminal commit. Prune expired completed/failed
receipts individually even while sessions remain live. Never evict unexpired
promised results or unresolved/unknown evidence at capacity.

The existing reviewed contract bounds deduplication by retention and surviving
Redis data. Arbitrary legacy string IDs cannot prove past use forever after GC.
Lookup beyond retained evidence is unknown_history, not proof that an effect never
ran. Producers must revalidate source/session after that window. Automatic
recovery must not use unknown_history to restart external business effects.
No new OperationReference API is required for this release; no global exactly-once
or indefinite deduplication claim is introduced.

Format1/2 conversion requires read-only assessment, backup, drained old writers,
explicit activation and preservation of pending/unknown/receipt identity. Python
and Rust must read/write identical formats and fingerprints. Engine switching
inside format3 needs no data conversion. Existing session/FSM/lock authority stays
unchanged; no whole-update authorization cache.

## Implementation ownership

- Sentinel: Python middleware efficiency, native memory limiter/debounce and parity.
- Cmds: explicit immutable compiled command snapshots and native resolved batches.
- Nav: format3 repository, canonical ledger, tracked adoption and native reducers.
- Idle: urgent patch, format3 combined ownership, native lifecycle/queue/guards.
- Independent review: shared storage/replay/native ABI/fencing/failure semantics.
- Root: baseline manifests, common benchmark protocol, integration/release audits,
  exact artifacts and PyPI/GitHub delivery. Existing Kit drafts remain untouched.

## Benchmark protocol

Compare published baseline, optimized Python, compatible existing serializer
comparator and custom native core. Record revision/engine/versions/CPU/OS/seed,
warmups/repeats, CPU/RSS, latency distribution, event-loop lag, Redis command calls
and bytes. Lua internal commands are not client network round trips.

Use pyperf and Criterion plus async complete-update workloads. Development timings
under concurrent compilation/tests are exploratory, not release qualification.
Final qualification runs matched repeated profiles serially after code freezes.
Deterministic CI gates use call budgets, storage slopes and correctness rather than
universal millisecond timings. Warm uncontended library budgets: <=5 unchanged
update and <=20 simple tracked adoption Redis round trips; application FSM,
authority, external effects, startup and contention are itemized separately.

Retain current real-Redis concurrency/crash/FSM/callback tests and add generated
Python/native traces, cross-engine codecs, malformed inputs, lost responses,
expiry/capacity and format migration tests. Preserve all four keyboard/control
styles and standalone/combined/mixed-engine profiles.

## Release isolation

Use separate native-vVERSION tags/GitHub releases and publish-native.yml so base
publish workflows' wheel wildcards never consume sibling distributions. Validate
exact asset allowlists, wheel metadata, wheel platform coverage, tag/versions and
independent SHA256 manifests before OIDC publication. New native publishers need
owner-authorized PyPI registration when qualified artifacts are ready.

Publish qualifying companions before matching bases. Nav precedes Idle; Sentinel
and Cmds are independent. Verify PyPI hashes and fresh index-only installations.
No PeopleHub application deployment or configuration change is included.

## Current status

Baseline tags and machine metadata are recorded in
reports/2026-11-11-optimization-program/baseline-manifest.json. A clean published
baseline environment is prepared outside the checkouts. Repository implementations
and audits are active. Idle0.2.1 is published: merge462cfe7,604local tests, two
greenCIruns, exactPyPIhashes andfreshstandaloneinstall verified. Sentinel/Cmds/Nav
nativecores are implemented and undergoing profiling; no native publication or
performance qualification is claimed.

Sentinel1.3.0 is published (PR65, merge3dc8da4, publish42924235432), hashes and
fresh standalone install verified. Its native distribution is withheld by the
measured gate. Cmds0.3.0 is published (PR18, merge1457341, publish42927553362), with
matching PyPI hashes and a fresh index-only standalone install verified. Its
native distribution is also withheld: the representative compiled-batch CPU
ratio was 1.567 (slower), so no native extra or release is advertised.
Nav/Idle format3 and integrated recovery implementation remain active.
