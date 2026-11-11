# Implementation verification

Historical local verification on 10 November 2026, before the 0.1.0 memory and Redis release.

## Implementation audit results

The table records the earlier implementation audit, before repository-convention
and packaging tests were added. It is historical evidence, not a claim that every
check was repeated during a documentation change.

| Check | Result |
| --- | --- |
| Python 3.12 / aiogram 3.31.0 development suite | 339 passed; 87.98% combined line/branch coverage |
| Python 3.10 / aiogram 3.22.0 / redis-py 5.0.8 | 339 passed with Redis |
| Python 3.14 / aiogram 3.31.0 / redis-py 7.4.1 | 339 passed with Redis |
| Independent wheel installation outside checkout | Redis extra: 339 passed; base: 273 passed, 66 server-only skips |
| Independent sdist installation outside checkout | Redis extra: 339 passed; base: 273 passed, 66 server-only skips |
| Clean installations with Redis and aiogram-idle absent | Passed for both artifacts |
| Ruff lint/format | Passed |
| Strict Pyright for source and examples | Zero errors |
| Typed distribution marker | Included |
| Wheel/sdist metadata via Twine | Passed |
| Navigation and Kit strict documentation builds | Passed |
| Dependency audit | No known vulnerabilities; unpublished editable package skipped |
| Source/test file-size and whitespace checks | Passed; Python files below 500 lines |

CI defines Python 3.10–3.14 with minimum/latest aiogram endpoints. Python 3.14
with aiogram 3.22 is excluded because that release pins dependencies predating
Python 3.14 support. Python 3.11/3.13 jobs are configured, not locally claimed as
executed. The CI workflow has not run remotely.

The follow-up [memory audit](memory-audit.md) adds 61 regression cases to the
initial 191-test slice. Current full runs use frozen reviewed source; remote CI
has not been executed.

## Behavior and failure coverage

Contracts test invalid identities, JSON types and size/depth limits, immutable
snapshots, timestamp serialization, generated registries, cycles, explicit roots,
abstract destinations, parameter validation and migration mappings. Canonical
fingerprints distinguish JSON true, 1 and 1.0.

Storage tests cover session recreation, guarded CAS, duplicate operations before
stale-version checks, bounded history, active controls and retained action receipts,
prepared versus committed views, expired authorization, late known receipts,
unknown-stage preservation and concurrent preparation. They also cover scoped
capability expiry, token actor/session/view ownership, operation-ID aliases,
tracked-view ABA rejection and repeated navigation beyond the active-token limit.

Runtime tests cover go/back/home/cancel/refresh, explicit cross-root transitions,
Back filtering across roots, tracking, manual prepare/complete, accepted touches,
background activity preservation, authorization denial, migration/safe-root
recovery, cancellation hooks, observational hook failures, partial rendering,
lost send responses and lost commit responses. Caller-modified prepared actions
cannot change the intent used for completion authorization. Denied refresh cannot
discard unresolved recovery evidence. Unknown business cancellation cannot be
silently replaced by a presentation refresh.

Presentation tests verify actual Telegram method shapes for reply, inline,
command-only and hybrid screens, explicit reply removal, compatible edits,
definite edit fallback, unchanged tray preservation and partial hybrid retries.
Recorded plans retain their display locale across recovery; newly resolved
locales cannot mislabel an old keyboard. Unknown sends are not automatically
repeated.

Dispatcher tests use real Dispatcher.feed_update with a recording Telegram
session. They exercise all four styles with FSM isolation enabled/disabled,
full-handler coordination, borrowing only the actual FSM lock, disabled FSM
middleware, post-install isolation changes, command mentions/arguments, installed
versus current tray locale, free typing, stale callback acknowledgement/cleanup,
actor spoof rejection, known external FSM builder identity validation, pending-render admission and callback retry after token
consumption. Back preserves drafts; explicit cancellation clears only owned fields.

All example CLI entry points execute --help without BOT_TOKEN. No real Telegram
messages were sent.

## Implementation review corrections

The initial implementation review fixed prepared-intent authorization forgery, denied
refresh abandoning evidence, unbounded effect metadata, token operation aliases,
obsolete-token accumulation, reused view generations, JSON numeric-type equality,
background activity timestamps and persisted-plan locale recovery. The subsequent
audit additionally fixed shared stage execution, live recursion markers,
per-stage authorization, preservation of older uncertainty, completion receipt
truth, malformed partial receipts, delivery constraints and setup-time FSM/context/
router invariants. Identity-resolver opt-outs now defer to application handlers.

## Boundaries

- Memory supports one event loop/process and loses state, tokens and recovery
  evidence on restart. Select Redis explicitly for persisted navigation; there is
  no automatic memory fallback.
- Redis navigation is implemented. The optional idle adapter lives in
  `aiogram_idle.integrations.nav`; see [integration](idle-integration.md).
  External session stores, multiple simultaneous navigation panels and a durable
  analytics outbox remain deferred.
- No idle package is imported or required. Navigation does not start idle workers.
- Application drafts/FSM transitions and authorization remain application-owned.
  A navigation commit is not a database transaction or exactly-once Telegram send.
- Reply labels and bare commands cannot prove their originating screen. Inline
  controls carry generation-specific provenance and expire on view replacement.
- Callback bindings use a dedicated router before business routers. Dispatcher
  root handlers that would outrank installed bindings are rejected.
- Unknown cancellation effects need explicit evidence-based application recovery.
  An explicit new presentation cannot retract an already in-flight request.
- Real iOS/Android/Desktop client UX was not manually tested.
- These tests send no real Telegram messages and perform no package publication
  or application deployment. Repository pushes and remote workflow outcomes are
  separate from these local verification results.

## Redis verification

The full local run uses Redis 7.4.11 in an isolated Docker container, redis-py
7.4.1, Python 3.12 and aiogram 3.31.0. Required-server mode prevents infrastructure
skips: `AIOGRAM_NAV_REDIS_URL=redis://localhost:6379/0 AIOGRAM_NAV_REQUIRE_REDIS=1`.
The 49 added cases cover memory parity, independent clients and runtimes,
renewal/loss/expiry of conversation leases, actor/session/view-bound callbacks,
full-handler FSM writes, stale raw-state reload, process exit after confirmed
partial delivery, unknown sends, lost commit responses, genuine partial Lua
errors, script-cache reload, retention/capacity, profile conflicts and damaged
history/indexes. Base installs skip server-only tests explicitly.

The Redis backend is optional and imports no aiogram-idle types. Infrastructure
failover/data loss, Cluster and an administrative index rebuild remain outside
this verification. Remote CI jobs are configured, not claimed as executed.


## Follow-up Redis audit

The [Redis audit](redis-audit.md) adds 38 regressions. The full development suite
passes 339 tests with 87.98% combined line/branch coverage. Python 3.10 with
aiogram 3.22.0/redis-py 5.0.8 and Python 3.14 with aiogram 3.31.0/redis-py 7.4.1
also pass all 339 tests. Shared FSM tests now use actual RedisStorage and
independent Redis clients, beyond the earlier shared-memory FSM tests.

Clean base wheel/sdist installs pass 273 tests with Redis and aiogram-idle absent;
66 infrastructure-only cases skip explicitly. Redis-enabled artifact checks run
the complete suite. Required-Redis verification fails if its dependency or server
URL is absent, rather than silently skipping infrastructure.

## Repository convention verification

The 10 November 2026 repository-convention baseline reran 339 tests against real
Redis on Python 3.12 / aiogram 3.31.0, with 88.78% combined line/branch coverage.
The standalone baseline passed 273 tests and explicitly skipped 66 server-only
tests. After adding three packaging contracts, the real-Redis development suite
passed 342 tests with 88.79% combined line/branch coverage. These results do not
relabel the older minimum-version and installed-artifact matrix results above.

Strict source/example Pyright and Ruff lint/format passed. Packaging checks
verify installed version agreement, `py.typed` and base installs without Redis or
aiogram-idle. [Security scan policy and local evidence](https://github.com/ArmanAvanesyan/aiogram-nav/blob/main/reports/README.md)
describe the full Bandit inventory, the medium/high severity gate and Linux
dependency audit. Generated JSON is retained as CI artifacts, not committed.
