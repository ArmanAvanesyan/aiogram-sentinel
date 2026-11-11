# Idle/Nav 0.2 performance and retention review

Investigated 11 November 2026. Proposal only: no library implementation, release,
application error mapping or deployment was changed. Package sources are the
released 0.2.0 trees. Investigation used isolated Redis 7.4.11, private namespaces
and no Telegram requests. This is separate from the existing design drafts.

## Findings

### 1. Confirmed: duplicated historical state is the primary growth defect

`Navigation.track()` goes through prepare, render-start checkpoint, render-confirmed
checkpoint and commit. Each phase writes the integration projection. The canonical
Nav ledger retains operations and their results. The projection serializes that
entire ledger into the opaque `aiogram_nav` component. Every generic Idle component
transaction then retains an entire RuntimeSnapshot as its own operation result.
That snapshot contains another full copy of the growing Nav ledger.

Relevant code:

- Nav `src/aiogram_nav/navigation.py:337` and `actions.py:359`.
- Idle `integrations/nav/engine.py:193` and `:229` serialize/commit the projection.
- Idle `storage/component_transaction.py:265` retains the complete updated snapshot.
- Idle `storage/redis_engine.py:128` decodes every receipt; `:189` re-encodes them.

This is duplicated bookkeeping, not a necessary cost of navigation or safe leases.
It gives quadratic retained bytes before caps and superlinear cumulative transfer
and serialization cost. History contributes bounded payload but is not the root:
Nav's `history_limit` really does slice the history, default 20. It cannot trim the
operation ledgers or their historical copies.

A fresh direct `track()` reproduction, alternating two nodes, measured:

| Tracks | Record bytes | Idle receipts | Bytes in receipts | Seconds/track |
| --- | ---: | ---: | ---: | ---: |
| 1 | 20,964 | 4 | 14,965 | 0.148 |
| 4 | 165,597 | 16 | 148,799 | 0.570 |
| 8 | 562,985 | 32 | 530,169 | 1.194 |
| 16 | 2,164,625 | 64 | 2,094,466 | 3.063 |

At 16, receipts account for 96.8% of the record. The last receipt alone is 67,354 bytes.
Each call made70 client execute_command invocations, constant in this fixture.
This excludes Dispatcher/FSM/application-authority overhead; it neither reproduces
nor disproves the consumer's130-command full-handler count. Local timings reflect
this host/Docker setup, not a portable latency SLO. Redis INFO commandstats also
counts Lua-internal commands and must not be labeled network round trips.

The 8 MiB component bound is not the envelope bound. Idle `storage/codec.py:45`
limits the complete serialized persistence envelope to 32 MiB (`encode` raises
Overloaded). A failure shortly after a 29 MB measurement could therefore be the
32 MiB envelope limit; it is not evidence the live component reached 8 MiB. Capture
the exact cause before assigning that original IdleError to either limit.

A separate memory/reducer reproduction reached24MB of encoded receipts at 64 tracks
and failed track 65 at 256 Idle receipts, while the canonical Nav ledger was 136 KB.

### 2. Capacity admission is real; the claimed broken TTL is not reproduced

Both libraries intentionally prune expired terminal receipts and reject admission
when unexpired/protected evidence fills the configured capacity. This follows the
previously reviewed safety requirement, but the integration's fourfold bookkeeping
makes its operational impact unacceptable. A default hour of retention plus256
slots is also a poor fit for high-frequency session binding/activity writes.

Idle `storage/receipts.py:59` prunes expired entries during prepare; Nav
`storage/memory.py:84` prunes completed/failed expired operations. A live session
need not expire before these receipts can be pruned. Whole-record expiry is a
separate mechanism and deliberately protects pending effects.

Controlled real-Redis tests with two writes per iteration and backend retention 2 s
completed 140 iterations / 280 writes without overload, retaining roughly 27–29 receipts.
A 2.1 s pause reduced retained receipts to 2 on the next operation. Advancing a manual
clock also prunes; sleeping while a fixed ManualClock stays unchanged does not.

Importantly, `IdleRuntime(config=...)` does not change the backend storage profile:
`runtime.py:75` selects runtime configuration, while RedisStore uses the
RedisIdleBackend constructor's config. Setting2s only on the runtime leaves backend
retention at 3600s. This is a possible source of the consumer observation, not proven
without their deleted harness. Add explicit storage-setting mismatch validation
and document configuration ownership. Do not report a confirmed retention bug.

Expired receipts are currently pruned on the next receipt prepare, not by every
read or reconciliation of a still-live conversation. Consequently physical bytes
can remain after logical expiry until another mutation. Add bounded expiry sweeping
or per-receipt expiry in the new layout; document the scheduling tolerance.

Another short-window hazard: the Redis reducer uses a clock sample taken before
READ/decode, and stamps receipt expiry using that frozen time. Expensive processing
can consume the replay window before COMMIT. The redesigned receipt TTL must start
from server commit time; test injected serialization delays. A 2-second test is not
a recommended production replay window.

### 3. Confirmed: repeated redundant Redis observations

A warm Idle store read currently makes four serial commands: GET namespace marker,
TIME, HEXISTS quarantine membership, READ script. A mutation adds COMMIT. Middleware
and action helpers repeatedly ask for prompt, busy, pending and current state.
The READ script already checks some of those invariants, but returns the complete
receipt-filled envelope. Both the number of observations and bytes per observation
need fixing.

Do not cache authorization for the whole update. Application session authority can
revoke independently of the conversation lock. Fold namespace validation, server
TIME and quarantine status into the authoritative READ script; share one parsed
observation only within an explicit decision phase, invalidate it after a mutation,
release/reacquisition or reentrant application callback. Mutation Lua must retain
namespace/config generation, expiry, lock ownership/fence, park and CAS checks.

### 4. Confirmed: abandoning the first prepared operation fails

Idle `integrations/nav/lifecycle.py:46` derives session only from pending/current
navigation. Abandon marks the first operation failed and clears pending; there is
no current screen yet, so compose raises ActivityConflict. The integration may
surface this as Nav VersionConflict, hiding the original cause, and leaves pending.

When no current/pending remains, compose may reuse the already-authoritative Idle
session only after validating matching generation/profile/owner and the abandoned
operation. Preserve absolute expiry; never invent or renew a session. Keep a failed
operation tombstone. Unknown/started external effects must retain their recovery
semantics; this fix is not permission to discard ambiguous business actions.

### 5. Clock warnings and application errors need precise classification

RedisClock currently anchors server TIME at response-processing time. A long
post-sample event-loop stall can look like a clock jump. The warning alone neither
proves server clock movement nor identifies the reported IdleError. Capture error
class/cause/stage, record size, lease remainder, sample RTT and event-loop lag.
Compare clock samples using request/response monotonic intervals, not one instant.
Do not raise lease/time limits to conceal pathological serialization cost.

The consumer should remove capacity errors from an unconditional503 retry list.
They need bounded, explicit application handling and alerts, with no repeated
business action or falsely reported navigation success. Infrastructure outages
remain separately retryable according to the application's idempotency policy.
A capacity failure while the screen was already rendered needs repair/degradation
policy; it cannot safely be treated as either an ordinary network retry or a
successful navigation commit. No consumer code was changed in this investigation.

## Proposed implementation

### A. Correctness/diagnostics patch, 0.2.1

1. Fix first-operation abandon with generation-preserving fallback and tests.
2. Reject conflicting runtime/backend storage settings with an actionable error;
   document backend-owned retention and lazy pruning. Preserve valid separation
   of runtime worker settings from storage settings.
3. Add structured capacity reasons/metrics: replay slots, protected evidence,
   bytes and earliest safe expiry. Keep existing Overloaded base compatibility.
4. Fold the redundant safety observations into READ while preserving every check
   and fresh Redis time. Add command-count tests and clock sampling diagnostics.
5. Explicitly test expired completed receipt pruning against real time and manual
   clocks. No automatic eviction of still-promised replay results in this patch.

### B. Bounded storage/performance release, Nav 0.3.0 then Idle 0.3.0

Use one canonical recovery/replay ledger per operation. For the combined adapter,
Nav's operation entry already owns intent, stage evidence, fingerprint and terminal
result. Add an explicit audited component-CAS capability that does not retain a
second Idle RuntimeSnapshot receipt. A lost commit response is recovered by rereading
and reducing against that canonical Nav entry; it must return the original result,
not whichever screen happens to be current. Duplicate fingerprints still conflict.
A compact ComponentCommitAck is useful, but by itself retaining four acks per track
would leave the same256-slot problem. Remove redundant internal receipt ownership,
not just the blob payload. Preserve default semantics for unrelated component APIs.

Separate hot navigation/activity state from completed receipts in Redis. Store
receipts by operation with a bounded expiry index, and fetch only the target receipt
when deduplicating. Commit state, receipt/stage, activity and deadline in one fenced
Lua transaction. Use Redis 7 compatible per-key TTL/index operations; no reliance on
newer hash-field expiry. Set completed receipt TTL from authoritative COMMIT time. Keep active/unknown/pending evidence outside automatic TTL
deletion and preserve bounded reconciliation. Memory uses the same reducer and
admission rules. No read should decode the entire receipt history for current state.

Give already-rendered `track()` an atomic adoption path. There is no new render call
to surround with started/confirmed checkpoints: validate and commit the supplied
message references, node, session, activity and deadline together. Retain one user
operation receipt. Cleanup or reply-overlay effects, when needed, use their own
explicit recovery stages; do not silently drop them to meet a benchmark. The
prepare/render/complete path remains for framework-owned external rendering. A
send before track that crashes before adoption is still outside library recovery.

Separate completed replay retention from unresolved-effect recovery retention.
Offer a documented shorter replay window and capacity sizing by peak operations
per second times window, rather than one hour applied to every internal stage.
Prune expired completed entries before admission. Preserve unresolved evidence.
Do not silently evict unexpired completed receipts under the existing contract.
If capacity-driven earlier eviction is later offered, it requires an explicit
weaker contract plus bounded replay-floor/operation-generation proof: an expired
retry must return ReceiptExpired/unknown, never restart effects as a fresh operation.
Arbitrary reusable string IDs alone cannot provide that proof after deletion.

Do not promise infinite throughput with finite replay memory. If protected evidence
fills capacity, reject admission with useful diagnostics; do not evict recovery.
Normal traffic must remain below that boundary through one receipt per user action,
short explicit replay windows, byte limits and predictable sizing.

## Acceptance gates

- Keep memory/Redis parity and standalone Idle, standalone Nav, combined modes.
- Reproduce1/10/50/500/5000 transitions with fixed payload/history caps. Active-state
  reads and target-receipt fetches must not grow with conversation age; total retained
  bytes stay O(current history + pending evidence + retained compact results).
- Assert no RuntimeSnapshot/components/full ledger inside integrated generic receipts.
- After replay expiry, >10 times configured capacity can proceed; within-window same
  ID returns original result and changed input conflicts. Expired retries cannot
  create another prompt, business cancellation or activity generation.
- At capacity, mixed pending/unknown/terminal cases preserve protected evidence.
- Lost responses at every commit stage, killed workers, expired leases, activity vs
  timeout, configuration change and external-session revocation retain old guarantees.
- Test first prepare/abandon/fresh navigation; wrong/expired generation still rejects.
- Warm uncontended budget: <=5 Redis command round trips for unchanged updates and
  <=20 for simple tracked adoption, including library coordination. Aim for one
  observation script and one commit script, not one total network exchange.
  Account separately for application authority, application FSM storage, cleanup,
  cold startup, contention and renewal. Never cache away these security boundaries.
- Measure client commands/bytes, Lua calls/time, encode/decode CPU, median/p95 and
  peak event-loop lag. Deterministic CI gates use counts/size slopes; latency numbers
  require a labeled benchmark host, not brittle universal millisecond assertions.
- New receipt/storage layout is an explicit next-format activation: backup, assess,
  drain old writers, migrate terminal entries, retain unresolved evidence, then enable.
  Never truncate live Redis blobs manually or run0.2 writers on the new namespace.

## Delivery order

Consumer error mapping can be corrected independently now. Then ship/test 0.2.1
correctness fixes. Implement the canonical-ledger and hot/cold layout against the
benchmark before enabling navigation again. Release Nav first, then Idle with the
matching optional Nav range; Coordination need not change unless its contract does.
For B5, standalone Idle remains a reasonable interim route after backend retention
is correctly configured and replay/capacity behavior is verified against the intended
webhook retry horizon. Do not deploy a 2-second deduplication window as a workaround. It should not
require adoption of Nav. Keeping BOT_NAV off meanwhile is reasonable.

## Reproduction artifacts

Saved under `reports/2026-11-11-idle-nav-performance/`: `combined-results.jsonl` and
`reproduce-combined.py`. The script imports the released checkout's existing test
builder, uses a unique prefix and counts client execute_command calls; it is a
research harness, not a proposed public API example. Run only on disposable Redis:

```sh
docker run -d --name aiogram-performance-review -p127.0.0.1:16520:6379 redis:7-alpine
../aiogram-idle/.venv/bin/python reports/2026-11-11-idle-nav-performance/reproduce-combined.py
```

It deliberately performs 16 tracks to demonstrate the slope without a multi-minute
50-screen run. No production keys or application data are used. Save output before
removing the disposable container. Future implementation should turn these cases
into portable real-Redis regression tests rather than retain test-helper coupling.

Additional retained evidence: `idle_receipt_perf_audit_results.json` and the
associated `idle_receipt_perf_audit.py` / `idle_redis_retention_audit.py` scripts;
`measure_combined_receipts.py` and `repro_first_abandon.py` preserve independent
reducer/recovery reproductions. These are local research scripts with checkout
imports, not release tests or production tools. The default-retention control
hit 256 receipts at iteration 128's second write (one initial receipt plus two
writes per iteration), confirming the cap independently of navigation.
