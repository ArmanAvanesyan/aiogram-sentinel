# Deterministic engines and bounded storage

The default engine is Python. It uses cached codec metadata, a linear registry
index and an expiry heap rather than repeatedly scanning terminal receipts.
`NavigationConfig(..., engine="python")` preserves the earlier positional
configuration parameters; the new engine option is keyword only. Memory and Redis
constructors also accept `engine=` explicitly.

`engine="rust"` requires the separately built, exactly matching
`aiogram-nav-native==0.3.0` companion. There is no native dependency or installation
extra in the base package. The companion is not published until the measured
performance gate passes. Presence of Rust source or a successful wheel build is
not evidence of a speedup. Local development can build it with Maturin from
`native/`; see its README and benchmark findings.

Engine acceptance checks the exact version, ABI, required functions and registry
methods before a backend can initialize its namespace. Missing binaries, loader
errors and incompatible capabilities raise `ConfigurationError`. No mutation or
failed effect falls back to another engine. Both engines keep Telegram requests,
application callbacks, locks, sessions, ownership and Redis I/O in Python.

The Rust core implements strict JSON parsing, registry validation/indexing,
history/state transitions, token comparisons and hashing of the original Python
canonical bytes. It does not reserialize floats to redefine existing fingerprints.
All valid Unicode scalars, including non-BMP characters, remain supported. Lone or
paired surrogate code units supplied as Python strings are rejected early, rather
than normalized or silently accepted in memory and rejected later by Redis. Valid
JSON surrogate-pair escapes decode to their corresponding non-BMP scalar.

## Fresh format-three Redis namespaces

```python
from aiogram_nav import NavigationConfig
from aiogram_nav.storage.redis import RedisNavigationRepository

repository = RedisNavigationRepository(
    redis=application_redis,
    prefix="application-navigation",
    storage_format=3,
    config=NavigationConfig(engine="python"),
)
await repository.initialize()
```

Fresh format-three initialization atomically establishes the profile, history,
format manifest and live-index witness. Explicit `storage_format=3` refuses an
existing format-one/two namespace: use the drained migration below. Omitting the
option preserves compatibility: fresh namespaces use format one and existing
namespaces are detected without an implicit upgrade. Memory storage also accepts
`storage_format=3`; it remains single-process and non-durable.

Format three separates the current projection from canonical operation rows:

- The hot record contains current navigation, active controls, external binding,
  revision and pending/current-owner references. It contains no operation history.
- Each canonical operation has its own STRING key, scoped by conversation and a
  SHA256 of its operation ID. The row verifies the complete conversation and ID.
- Terminal rows expire physically through Redis `PXAT`, anchored to `TIME` in the
  terminal commit. Rewriting a terminal integration payload preserves its original
  deadline. Prepared/unknown rows have no automatic TTL.
- Metadata contains row-key/status/control-index information, not another snapshot
  or delivery receipt. Bounded expiry cleanup removes at most a page per update;
  `sweep()` reclaims inactive conversations and remaining index metadata.

Reads fetch only requested operations, current/pending owners, indexed controls
and a bounded expiry page. They do not download all retained receipts. A missing
row before its promised expiry, a missing protected row or inconsistent ownership
metadata fails closed. An expired row may be absent only after the server's expiry
cutoff. Active controls are independent of terminal replay retention, so a still
current keyboard does not become invalid just because its render receipt expired.

The replay promise is finite: `recovery_seconds` defaults to 3600 seconds from the
terminal commit. In Nav this setting controls terminal receipt retention only;
prepared and unknown operations have no automatic expiry. Unexpired receipts and unresolved evidence are never evicted to
admit another operation. Capacity exhaustion raises `Overloaded`. Expired terminal
receipts can be reclaimed, allowing paced traffic to exceed lifetime capacity.
`ActionStatus("not_found")` means **not retained**, not **never executed**. After the
advertised window, producers must revalidate their source and session; arbitrary
string IDs cannot provide permanent global deduplication. Unknown external stages
remain protected and are never automatically replayed.

## Atomic adoption and optional component hosts

`track()` adopts a screen already rendered by the application. Default memory
storage, and Redis after format-three activation, can prepare and complete that
adoption in one guarded mutation through `adopt_render(...)`. Authority is checked
again after application guard/locale callbacks. Events and generation-specific
cleanup run after commit. Invalid inputs or failed pure reductions do not expose a
partially accepted activity. A crash before calling `track()` still belongs to the
application's rendering workflow; use prepared rendering for recoverable sends.

`AtomicAdoptionRepository` is an optional capability. Legacy/custom repositories
choose the earlier sequence before mutation. An atomic failure is never retried
through that sequence. Custom subclasses conservatively retain their public
method hooks unless they explicitly opt into the atomic capability.

Optional hosts such as aiogram-idle use the public `LedgerRead`, `LedgerDelta` and
`NavigationLedgerReducer`. Its `repository` executes pure bounded operations;
`record`/`replace_record()` support a validated owned normalization view.
`integration_payload()` returns a detached first accepted activity result from the
canonical operation, never the current screen. A host commits the delta, activity,
deadline and authority binding in one fenced transaction. It must not keep another
historical navigation snapshot or acknowledgement ledger. Navigation stays usable
without Idle, and Idle does not become a base dependency.

## Migration and verification

Drain all old workers before explicit activation. The profile/history rotation
fences old readers and writers; changing a flag without actually draining in-flight
external effects is insufficient.

```sh
# Read-only assessment; supplies no approval or activation implicitly.
uv run python tools/migrate_storage.py --target 3 --expected 1
# Explicit upgrade after all old workers have drained.
uv run python tools/migrate_storage.py --target 3 --expected 1 --apply \
  --operation-id navigation-format3 --old-workers-drained
# Optional bounded eager conversion after activation (otherwise conversion is lazy).
uv run python tools/migrate_storage.py --target 3 --migrate-all \
  --batch-size 100 --max-pages 100
```

Use `--expected 2` for a format-two namespace. These commands use the existing
Redis environment variable and namespace prefix options. Record conversion is one
atomic CAS after pure off-thread conversion; interruption can be resumed. Original
absolute replay deadlines are retained, and unknown/protected operations survive.
An old-format envelope is distinguishable from partial/corrupt format-three state;
corruption does not trigger legacy fallback. The page cursor contains only offsets.
With concurrent admissions, repeat assessment/passes as with any SSCAN traversal.

`benchmarks/run.py` runs against the **installed distribution**, without inserting
`src` into the import path. It records fixed-payload track workloads aged 50, 500 and
5000 receipts, CPU medians, individual latency median/p95, versions and hardware.
`--redis-url` adds whole protected `Dispatcher.feed_update` measurements, exact
consumed RESP bytes, library round trips, separate Lua command counts and cold
bootstrap diagnostics. It removes only its newly generated benchmark prefixes.
Every driver result sets `qualification=false`; the independent release gate owns
qualification. `--quick` is only a smoke test. Normal CPU results use at least ten
independent batches, and individual-update p95 uses nearest-rank sampling.

Run full comparisons serially on the same machine. The native publication gate
requires at least 20% representative CPU benefit and no greater than 5% realistic
p95 regression against optimized Python. Published baseline comparisons, optimized
Python and Rust results must remain separate; unsupported baseline capacity is
reported as unavailable rather than replaced with invented timing values. Pyperf
kernel probes are provided in `benchmarks/pyperf_codec.py`, and Criterion lives in
`native/benches`.

### Capacity and authoritative host generations

Size `max_receipts` for the promised window: peak accepted operations per second
multiplied by `recovery_seconds`, plus headroom for protected unfinished or unknown
effects. The defaults (256 receipts and a 3,600-second replay window) are finite.
Atomic adoption retains one operation instead of four stage snapshots; it does not
remove admission limits. For example, 2 operations/second and a 60-second window
need 120 terminal slots; 256 slots leave 136 for protected work and bursts. Never
shorten the business recovery promise to disguise insufficient capacity. The
5,000-operation slope benchmark explicitly configures 10,000 slots; separate tests
exercise default-capacity rejection and more than ten capacity windows of paced
traffic.

Canonical component hosts call the pure
`NavigationLedgerReducer.bind_session_generation(session_id, expires_at)` before
preparing an action or selecting its scoped view index. This hook requires an
already verified host session; it performs no authorization or network access.
The host fences the final atomic commit against that observation. Fresh Nav
state uses the host's absolute deadline from the start. A live legacy generation
with an earlier Nav deadline keeps that deadline. An expired Nav generation
cannot reopen under the same session id, even if its host still has time left;
replace the host generation explicitly. Pending effects retain their original
session and deadline. Ordinary standalone Nav generation ownership is unchanged.

Format 3 stores view ownership under a session-scoped hash. A separate integer
index-count witness detects missing reverse-index fields before reads, garbage
collection or writes. Selected pointers are validated against their canonical
owner row. Coordinated external modification of both the index and its witness
is outside the storage corruption model; Redis keys remain library-owned.

### 0.3.0 native qualification result

The independent repeated serial installed-artifact gate did not qualify the
native companion for publication. Rust consumed 21.7% more process CPU than the
optimized Python engine on the preselected `memory-track/50` workload; its
individual-update p95 was 22.4% higher. Whole-handler Redis latency remained near
parity, which does not satisfy the required 20% CPU benefit. The pure Python
package can release independently. Native source and platform CI remain, but no
native PyPI package, release tag or `[native]` extra is published for this result.
Selecting Rust requires an explicitly built, exact-version local companion;
ordinary installations continue to use Python.
