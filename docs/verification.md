# Implementation verification

This page retains dated implementation/audit evidence. Statements about local-only
work describe those runs, not the repository's current publication or push status.
Repository-alignment verification subsequently passed 508 existing tests with
89.27% combined coverage, plus three new distribution-contract tests separately.
See the [alignment report](https://github.com/ArmanAvanesyan/aiogram-idle/blob/main/reports/2026-11-10-repository-alignment.md)
for its exact commands, security scope and remaining boundaries.

Verified locally on 10 November 2026 for the unpublished 0.1.0 distribution,
including the optional navigation projection and its concurrency, recovery, FSM and keyboard tests.

## Historical implementation results

| Check | Result |
| --- | --- |
| Python 3.12 / aiogram 3.31.0 / redis-py 7.4.1 / Redis 7.4.11, frozen source | 471 passed; 89.19% combined line/branch coverage |
| Python 3.14 / aiogram 3.31.0 / redis-py 7.4.1, frozen source | 471 passed |
| Python 3.10 / aiogram 3.22.0 / redis-py 5.0.8 | 389 core cases plus all 82 optional cases passed across the core/optional/boundary runs |
| Fresh wheel with nav/redis, redis-py 5.0.8 | 91 optional/component/ownership cases passed outside checkout |
| Fresh sdist with nav/redis, redis-py 5.0.8 | Same 91 cases passed independently |
| Standalone wheel/sdist, nav absent | 389 core cases passed for each; optional modules skipped explicitly |
| Base wheel/sdist, Redis and nav absent | 232 cases passed for each; infrastructure/optional cases skipped explicitly |
| Final base and Redis-only artifact import boundaries | Passed; missing nav import gives installation guidance |
| Frozen standalone checkout sync without peer checkout | Passed |
| Ruff lint and formatting | Passed |
| Strict core and optional source/example typing | Zero errors |
| Wheel/sdist metadata through Twine | Passed |
| Example compilation, CLI help and four-style Dispatcher example tests | Passed |
| Installed dependency audit | No known vulnerabilities; unpublished local packages skipped |
| Kit strict documentation build | Passed |
| Whitespace and Python file-size checks | Passed; files below 500 lines |

The 471 unique cases comprise 389 core tests and 82 optional navigation tests.
Earlier full endpoint runs passed 443 cases; subsequent optional runs cover the
added keyboard/schema/business-recovery cases, and the final minimum-version
boundary run covers shutdown ordering. The frozen Python 3.12/3.14 runs execute
the entire final suite in one command. Artifact core suites were run before the
last optional-only changes; final core files were verified byte-for-byte equal
and the rebuilt artifacts reran the optional suite plus component/ownership tests.

The audit adds 69 regression cases to the earlier 311-test implementation. See
[the findings and fixes](redis-audit.md) for the corrected contracts. The final
full runs used frozen source; clean-artifact runs imported installed packages
outside the checkout rather than editable source.

Earlier memory-only compatibility runs also passed on Python 3.11 and 3.13. CI
covers Python 3.10–3.14, minimum/latest aiogram endpoints and Redis 7/8 with
minimum/latest supported redis-py clients. Python 3.14 with aiogram 3.22 is
excluded because that release pins dependencies predating Python 3.14 support.
The updated CI workflow has been checked locally but has not run remotely.

## Behavioral coverage

Shared contracts cover guarded sessions/activity generations, immutable
snapshots, deduplicated operations, fingerprint conflicts, expiry, configuration,
controls, capacity and retention. Redis tests use actual isolated servers and
independent clients/processes rather than an emulated Redis.

Recovery tests cover competing workers, expired claims, killed claiming processes,
stale acknowledgements, lost commit responses, reconnection, script-cache loss,
confirmed receipts, uncertain sends, exhausted retries and Continue/Cancel/timeout
races. Atomic tests interpose between reads and commits to verify namespace and
configuration-loss fences, immutable profiles, parked-state fencing, validated
claim snapshots, heartbeat replay ordering and delegated effect capabilities.

Corruption tests reject invalid identities, policies, jobs, receipts, tokens,
unsupported schemas and binary data without overwriting recovery evidence.
Queue tests cover missing jobs, orphan due entries, reconciliation continuing
past corrupt work, bounded scan overflow, index reconstruction and explicit
release after repair. Retention admission is checked with 128 live claims ahead
of a prunable terminal record.

Dispatcher.feed_update tests verify full-handler protection, enabled/disabled FSM
isolation, consistent local/distributed lock ordering, actual borrowed-lock
identity, unchanged middleware configuration and lossless Redis FSM keys. They
also verify separate dispatchers sharing Redis FSM state and raw-state reload
after acquiring ownership. Revoked scopes cannot reacquire, delegated effects
cannot use another conversation's capability, and timeout/lease cancellation
consumes only its own request. These cancellation cases run on CPython 3.10 as
well as modern Python.

All four prompt styles use the Redis runtime with fake Telegram sessions. No real
bot messages were sent.

## Limits and deferred capabilities

- Memory remains single-process and loses all state on restart.
- Redis infrastructure persistence, replication, rollback and Sentinel failover
  were not qualified. Process-crash recovery assumes authoritative Redis data
  survives; lost history cannot reconstruct external effects.
- Redis Cluster, external session-store integrations and a durable analytics
  outbox remain deferred. The optional navigation adapter is implemented separately. Core and Redis need no aiogram-nav.
- Custom FSM isolation requires a supported adapter and is rejected. Redis FSM
  builders must include bot identity; selecting idle Redis storage does not
  persist application drafts or a memory FSM.
- Unknown business outcomes require evidence-based recovery. Leases cannot
  retract in-flight Telegram/database requests; application writes still need
  generation guards and idempotency.
- Real Telegram-client UX on iOS, Android and Desktop was not manually tested.
- Existing older Redis layouts require explicit migration, never automatic
  history/configuration replacement.
- Changes remain local and uncommitted. No publication, push or deployment occurred.

The dedicated Redis test containers were removed after verification.


## Optional navigation integration

The integration runs a separate four-style/two-backend matrix. Tests assert atomic
nav/activity/deadline updates, mapped counters and exact touch receipts, inherited
policies, explicit restarts, no acceptance from background renders, prompt-control
precedence, shared memory/Redis FSM coordination and shutdown ordering. They also
cover process exit after confirmed rendering, failed final cancellation commits,
unknown deliveries, malformed component parking and lost/replaced claims.

Reply/hybrid tests inspect actual Telegram method arguments after Continue,
Cancel and ordinary accepted input. They verify application keyboard restoration,
explicit and implicit removal, silent restoration, durable background recovery,
no extra accepted activity and no repeated business cancellation. The canonical
presenter receives temporary-keyboard provenance through an optional wrapper;
standalone hybrid delivery behavior is unchanged.

See [the integration guide](navigation.md). The manual peer-repository CI workflow
covers Python 3.10–3.14 and an additional Redis 8 job; no remote CI execution is
claimed. Publication, Kit dependency extras, external session-store transactions,
Redis Cluster and durable analytics outboxes remain separate milestones.

## Follow-up integration ownership review (10 November 2026)

The subsequent review added guards against changing reserved adapter/hooks or
coordination after binding, including changes while an FSM handler awaits its
lock. Unsupported custom/no-op coordinators fail admission, and rejected
installation restores presenter/writer bindings. Node policy mappings are frozen.

Component transactions reject unrelated-slot insertion and changes to a live
idle effect ledger. Finalization verifies the staged navigation reservation,
canonical identities and retained receipts; interrupted prepare retries preserve
existing render intent. A cached resume reservation cannot be reused to restore
a different screen. That eligibility-change case fails closed and needs explicit
operator recovery rather than automatically retargeting an uncertain operation.

Separate idle effect recorders in one coordination scope now share stage and
checkpoint locks, preventing repeated replay-safe effects in delegated tasks.
Observational hook failures remain separate from committed business actions.

Verification: 213 affected integration/component/core tests passed against a
private Redis 7.4 server before the final effect-locking regression; the final
134-case focused suite (including all new review cases, Redis recovery, memory
contracts and the new recorder regression) passed after those final changes.
Ruff and both strict Pyright configurations passed. Wheel/sdist builds and Twine
checks passed, and the wheel's Redis extra imported memory/Redis backends in a
clean environment with aiogram-nav absent. The earlier full-matrix figures above
remain historical evidence; this follow-up did not rerun that entire matrix.
