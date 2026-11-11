# Pre-implementation design review

Status: reviewed and corrected, 10 November 2026. This is a specification review; runtime guarantees remain subject to implementation and the release tests below.

The review covers standalone idle, Redis recovery, optional navigation integration and consistency across the programme, APIs and test plans. Both libraries remain independently usable. No application flow, ticket or deployment is a library release dependency.

## Findings and corrections

| Finding | Correction | Required implementation evidence |
| --- | --- | --- |
| Session/key reuse could let delayed work affect a new activity | Fresh activity_id, expected-generation guards, guarded session replacement and tombstones | Same-key ABA and stale touch/clear tests |
| Standalone examples depended on an external session without defining ownership | Idle-owned session factory plus explicit external SessionAuthority | Handler-only example without FSM/nav; fixed absolute expiry |
| Reusing one update ID for several mutations could deduplicate the wrong operation | Stable substep IDs and canonical-input fingerprints; payload mismatch is an error | Repeat same request, mismatch payload and delayed replay |
| Stale-control promise exceeded reply/command transport capabilities | Strict prompt binding only for token-bearing controls; current-activity semantics for text/commands | Delayed reply/command tests and unknown-delivery tests |
| Accepted ordinary input was reserved before knowing whether the handler succeeded | Supersede on explicit successful activity under full-handler coordination | Failed input preserves grace; successful input supersedes once |
| Recovery retention was incorrectly counted against user session lifetime | Separate logical expiry and physical retention; inspect eligibility before questions | Short-lived session with long receipt retention |
| Late send receipts could extend grace | Anchor to validated server delivery time or conservative request-start time | Receipt delayed past grace; no renewed response window |
| Navigation promised recovery but exposed only a final commit | Prepare/checkpoint/lookup/complete contracts and effect-stage recording | No send before durable prepare; unknown render never blindly repeated |
| Atomic integration could erase its own operation or diverge revisions | Operation-scoped staged replacement, adapter-owned writer, explicit mapping rules | Continue/restore staging, background render and activity mapping |
| Idle expiry/clear could delete retained navigation | Independent component retention and generation-scoped cleanup | Exempt view survives idle clear; old reply tray cannot overwrite new UI |
| Lease renewal and final acknowledgement checks were insufficient | Every worker write checks live ownership; late renewal cannot resurrect a lease | Paused worker, late receipt and expired renewal tests |
| Job lease was confused with conversation lock lifetime | Verify/renew both resources; reject unsafe isolation defaults | Disabled FSM isolation, short lock TTL and child-task tests |
| Reconciliation could not discover a missing due entry | Explicit live/expiry indexes with bounded cursors; administrative fallback for index loss | Lost due entry repaired; missing membership reported honestly |
| Atomic Redis scripts were treated as rollback transactions | Validate before writes, distinguish runtime inconsistency, NOSCRIPT and unknown execution | Script error, SCRIPT FLUSH, connection loss and noeviction profile |
| Idempotent abandonment was incorrectly generalized to all UI restoration | Per-effect receipts and EFFECT_UNKNOWN/QUARANTINED outcomes | Crash inside custom adapter; no whole-adapter replay |
| Replica-local enablement and policy changes could reinterpret active work | Versioned manifest, frozen active policy snapshots and explicit migration/drain | Mixed rollout versions and disable/re-enable races |

## Guarantees and limits

The backend conditionally commits state and schedules work atomically within its supported storage profile. It does not transact with Telegram, an application database or separately owned FSM data. Application effects need stage idempotency and business-version fencing. Redis data loss can remove the evidence needed for deduplication; a lease cannot stop a Telegram request already in flight.

Unknown delivery, unsupported persisted versions and exhausted retries stay visible instead of being silently retried or dropped. Recovery must distinguish a known unsent stage from an unknown effect. Memory provides the same live-process state semantics with no restart durability.

Redis execution and script-cache corrections follow the primary [transaction documentation](https://redis.io/docs/latest/develop/using-commands/transactions/) and [Lua documentation](https://redis.io/docs/latest/develop/programmability/eval-intro/). Lock integration was checked against the [aiogram FSM middleware](https://github.com/aiogram/aiogram/blob/dev-3.x/aiogram/fsm/middleware.py); exact supported versions still require integration tests.

## Implementation entry gate

Before implementing side effects, complete M0 with executable model fixtures for the corrected transitions and public error/result types. Then follow each package's memory, Redis and optional-adapter work packages. Standalone releases have no dependency on completion of the optional adapter.

Documentation checks verify rendering, links, code-block syntax and consistency; they do not substitute for the real-Redis concurrency, injected crash, dispatcher integration and manual Telegram-client tests specified in [storage and verification](storage-and-verification.md).
