# Four-library optimization and optional Rust implementation

Approved implementation, 11 November 2026. Implementation and releases are
complete. This document records the approved contracts and verified delivery; benchmark limitations remain explicit.

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
Nav's prespecified CPU gate is standalone memory-track/50, accompanied by
whole protected Dispatcher unchanged/tracked Redis updates at age50 for tail
checks. Registry compilation is a separate startup diagnostic; fixed-history
50/500/5000 receipt-age stress runs establish storage/call slopes independently.
Idle's prespecified CPU gate is standalone memory-activate-touch/50 (nine touches
per activation, fixed draft and immutable external session),10 batches of500
operations. Tail checks require standalone Redis activation/touch, the combined
protected Dispatcher no-op and combined Redis tracking,500 individual operations
each. Both exact Nav peer artifacts are fixed across engine profiles; Python
remains explicitly selected in Python runs. Queue claiming is a separately measured workload; event-loop lag remains an
untimed diagnostic. Four balanced serial profiles run after
freezing all installed artifacts and benchmark helpers.
The root evaluator requires unique runs, matching artifact and driver digests,
finite positive measurements and valid operation/sample counts. Historical failed
Sentinel/Cmds gates precede this provenance hardening; they authorize no native
publication and cannot qualify through the newer evaluator without new evidence.
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
reports/2026-11-11-optimization-program/baseline-manifest.json. Published baseline and candidate environments were isolated outside the
checkouts. Repository implementations, independent audits and releases are
complete. Idle0.2.1 is published: merge462cfe7,604local tests, two
greenCIruns, exactPyPIhashes andfreshstandaloneinstall verified. All four native
cores are implemented. No native companion is published or performance-qualified.

Sentinel1.3.0 is published (PR65, merge3dc8da4, publish42924235432), hashes and
fresh standalone install verified. Its native distribution is withheld by the
measured gate. Cmds0.3.0 is published (PR18, merge1457341, publish42927553362), with
matching PyPI hashes and a fresh index-only standalone install verified. Its
native distribution is also withheld: the representative compiled-batch CPU
ratio was 1.567 (slower), so no native extra or release is advertised.
Nav0.3.0 is published (PR2, mergea5a0696, publish42936943326), with exact
PyPI hashes and a fresh index-only standalone install verified. Its Rust
companion is withheld after a stable21.7% CPU regression. Idle0.3.0 is published (PR3, merge04a753a, publish42943214622). PyPI hashes and
fresh index-only standalone/combined installs pass. Its native core failed the
CPU gate (ratio1.066) and remains source-only. Final CI and post-merge CI pass.

The final audit added session-scoped retained-view indexes and an independently
checked index-cardinality witness to Nav's format-three work. Missing ownership
index evidence must fail closed. Combined hosts bind their verified session
generation before preparing or selecting an index; they may not rewrite it after
adoption. Fresh combined navigation uses the host absolute expiry. Existing
shorter navigation expiries remain immutable and cannot be reopened under the
same generation after expiry. These changes passed independent audits and real-Redis engine matrices.

Benchmark tooling is isolated and provenance-checked, with101 tests and
CPython3.10/3.12/3.14 CI. Kit PR3 carries the complete raw evidence, reports and
rendered charts. Pre-existing uncommitted Kit drafts remain excluded.
