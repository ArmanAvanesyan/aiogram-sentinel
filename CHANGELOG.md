# Changelog

<!-- towncrier release notes start -->

## [0.1.0] - 2026-11-10

### Miscellaneous

- Align repository automation, typed distribution checks, community
  documentation
  and changelog fragments with the related aiogram libraries. Runtime version
  reporting now reads the installed distribution metadata.


### Core library

- Introduce standalone conversation identity, session/activity guards, policies and typed adapter contracts.
- Add single-process memory storage and a recoverable inactivity lifecycle.
- Add reply, inline, command and hybrid prompt controls with aiogram dispatcher integration.
- Include ordinary-handler and FSM examples, deterministic tests and packaging checks.
- Add optional Redis 7+ storage, renewable distributed coordination, atomic indexes, retained operation receipts and explicit administrative index recovery.
- Exercise real-server worker races, process crashes, lease expiry, uncertain commits, corruption and memory/Redis parity.
- Include optional navigation integration as detailed below.

### Memory and lifecycle audit fixes

- Share backend coordination across runtimes and verify FSM borrowing/scope lifetimes.
- Enforce grace deadlines during answer admission and preserve original delivery grace on recovery.
- Serialize effect stages, preserve typed receipts and retain confirmed subeffects across retry/recovery.
- Guard reserved business work from reentrant/public mutations and ordinary handler admission.
- Protect pending evidence, expire administrative receipts, route namespace/bot claims and tag operation lookup results.
- Expand automated coverage to 168 tests, including 1,000 abandoned-claim recoveries.

### Redis audit fixes

- Fence namespace/configuration history, storage profiles and delegated effect checkpoints atomically.
- Prevent revoked-scope reentry and enforce shared FSM lock order and lossless Redis FSM keys.
- Repair missing/orphan queue jobs, isolate corrupt work and bind claims/quarantine to validated snapshots.
- Preserve unknown business-effect ledgers and validate action receipts before completion.
- Recheck grace before delivery, order heartbeat retries and preserve external cancellation through timeouts.
- Document backend scope contracts and explicit recovery in docs/redis-audit.md.

### Optional navigation integration

- Add the optional nav extra and aiogram_idle.integrations.nav projection without peer imports in either core.
- Commit navigation/activity/deadline updates in one memory/Redis transaction with mapped sessions and acceptance counters.
- Resolve inherited node policies, explicit activity groups and guarded touch/restart semantics.
- Share one coordinator and combined dispatcher middleware with verified FSM borrowing and prompt-control precedence.
- Stage Continue/Cancel/restore rendering under existing idle operations and preserve exact worker claims through recovery.
- Park unknown/schema-incompatible recovery without resending; retain typed receipts across process exit and final-commit failure.
- Restore temporary reply/hybrid keyboard overlays through durable background work and silence restoration sends.
- Preserve application cancellation uncertainty in a nested business effect stage.
- Add a runnable four-style example, standalone artifact checks and a separate optional-integration CI matrix.
