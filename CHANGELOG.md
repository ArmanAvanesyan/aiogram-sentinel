# Changelog

<!-- towncrier release notes start -->

## [0.3.0] - 2026-11-11

### Features

- Add explicit Python/Rust deterministic engine selection, with a separately built
  `aiogram-idle-native` 0.3.0 ABI 1 companion. Python remains the default; invalid
  native selection fails before initialization and never falls back after mutation.
- Add opt-in storage format 3: bounded current state, protected pending evidence,
  server-time anchored physical receipt expiry, immutable original result blocks,
  bounded reconciliation and effect-free staged migration with verified cutover.
- Add independently configurable completed replay retention, inheriting existing
  recovery retention by default. Preserve unexpired replay and unknown effects
  rather than evicting them under pressure.
- Fuse standalone activity activation into one canonical receipt and combine
  navigation operations with their first activity result in one canonical ledger.
  Application-owned adopted renders commit navigation/activity/deadline together.
- Reuse one decision observation inside combined middleware while keeping external
  authority checks fresh. Add installed-package workload benchmarks and explicit
  format 3 Python/Rust, real-Redis and mixed-engine verification profiles.

### Behavior changes and fixes

- Fresh combined navigation uses the verified Idle absolute session generation
  upfront. Existing shorter legacy navigation caps remain immutable; expired
  generations require explicit replacement. Navigation milliseconds never round
  authorization expiry upward.
- Serialize canonical external stages across recorder instances, reject recursive
  stage reuse, and preserve guarded explicit replay of safe uncertain effects.
  Check deadline claims again after application authorization hooks.
- Validate UTF-8 Unicode scalar identifiers and JSON early, consistently across
  engines and backends, without replacing or normalizing valid Unicode.
- Preserve original receipt expiry through rewrites and migration; fail closed on
  missing promised rows, reverse-index corruption or contradictory cleanup proof.


## [0.2.1] - 2026-11-11

### Bugfixes

- Preserve the authoritative session generation and expiry when abandoning the
  first
  prepared navigation view. Reject runtime/backend storage-setting conflicts
  while
  allowing separate worker settings. Fuse Redis history, parking and fresh time
  observations into the atomic read; retain all commit fences. Expose
  payload-free
  capacity reasons and clock sampling diagnostics, with regression coverage for
  lazy
  receipt expiry and promised replay retention.


## [0.2.0] - 2026-11-10

### Features

- Add shared task-scoped coordination, verified application isolation,
  read-only application session authority, immutable activity registrations,
  coarse analytics adapters and explicit staged Redis format activation. Extend
  optional Nav integration with manual router placement and application-owned
  prepared rendering while preserving atomic navigation/activity updates.
- Require `aiogram-coordination>=0.1.0,<0.2`; the optional integration now uses
  `aiogram-nav>=0.2.0,<0.3`. Public session authority observations use immutable
  millisecond expiry contracts; see the 0.2 migration guide before upgrading.
- Add strict managed-Redis deployment attestation, explicit old-worker-drained
  format activation, retained-evidence CAS migration and a dry-run-first
  administrative CLI. Existing format-1 namespaces remain format 1 until activated.

### Bugfixes

- Drain standalone managed idle workers before aiogram closes FSM storage and
  isolation; preserve uncertain effects and application authority during expiry
  and outages.


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
