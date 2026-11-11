# Changelog

<!-- towncrier release notes start -->

## 0.3.0 (2026-11-11)

### Features

- Add explicit Python/Rust deterministic engines, cached codec and registry
  indexes, heap-based memory retention and atomic adoption of application renders.
- Add opt-in Redis format 3 with canonical per-operation receipts, physical
  terminal TTL anchored at server-time commit, bounded selected reads and scoped
  view-ownership indexes. Capacity never evicts promised or uncertain evidence.
- Add drained-writer activation and restart-safe migration preserving original
  terminal deadlines and protected effects. Existing namespaces retain legacy
  behavior until explicit activation; fresh namespaces can select format 3.
- Let canonical component hosts bind a verified session generation before view
  ownership checks. Fresh navigation uses the host absolute expiry; live legacy
  shorter deadlines remain immutable. An expired same-id generation cannot reopen
  or extend: replace its host generation explicitly. Idle integration stays optional.
- Retain functional Rust source and platform/parity CI, but withhold native PyPI
  publication, native release tags and a native installation extra: independent
  serial qualification measured Rust 21.7% slower than optimized Python on the
  preselected memory-track/50 CPU workload. The optimized Python whole-handler
  Redis profile uses three round trips for no-op and eight for tracked navigation.

### Bugfixes

- Reject non-UTF-8 identifiers and JSON strings before effects or persistence,
  preserving valid Unicode and non-BMP scalars. Earlier ephemeral-memory
  acceptance of surrogate code units is no longer supported.

## 0.2.0 (2026-11-10)

### Features

- Add the shared aiogram-coordination dependency and verified application-owned
  FSM isolation through TrackedEventIsolation and structural coordinator adapters.
- Add manual binding-router placement with explicit root-handler opt-in, retaining
  automatic installation's strict routing safeguards.
- Add ApplicationPresenter and prepared Go/Back/Home/Cancel/Refresh actions so
  applications can own rendering and generation-specific message cleanup.
- Bind internal navigation generations to an external SessionAuthority without
  extending or replacing application sessions; retain uncertain recovery evidence.
- Customize stale/foreign callback rejections without consuming valid controls
  before application state guards.
- Add bounded draining and preserve caller-owned clients during shutdown.

### Redis and migration

- Keep storage format 1 as the default and add explicit format 2 activation with
  dry-run assessment, retained receipts and atomic fencing of old writers.
- Add managed Redis deployment attestation for ACL-denied inspection commands;
  observed unsafe deployments and connection failures still fail closed.
- Add real Redis 7/8 and minimum/current dependency verification. Navigation still
  works independently of aiogram-idle; no Idle dependency is introduced.

## 0.1.0 (2026-11-10)

### Features

- Add independent navigation contracts, immutable registry and versioned JSON codec.
- Add single-process memory sessions, guarded actions, history and bounded operation/control evidence.
- Prepare rendering before effects and retain confirmed/unknown stages for explicit recovery.
- Add text presentation with reply, inline, command-only and hybrid navigation.
- Add scoped/localized input bindings and actor/session/view-bound opaque callbacks.
- Coordinate full dispatcher handlers and verified FSM isolation without owning business drafts.
- Include runnable examples, user guides, contract/failure tests and a compatibility CI matrix.
- Keep aiogram-idle integration optional and outside this package; the adapter is supplied by aiogram-idle.

### Memory recovery fixes

- Serialize stages across recorders/runtimes, preserve prior uncertainty and recheck authorization before new effects.
- Bind completion to confirmed message receipts and strictly validate partial delivery plans/results.
- Preserve forced fresh-send recovery semantics and actual installed-keyboard locale provenance.
- Verify unchanged FSM storage, context identity, key mapping, coordinator and router precedence.
- Handle identity-resolver opt-outs, strict actor identities and valid millisecond expiry timelines.
- Record the audit and additional regression coverage in docs/memory-audit.md.

### Redis backend

- Add optional standalone Redis repository, server-time CAS and renewable fenced conversation locks.
- Persist snapshots, partial-render receipts and atomic actor/session/view control consumption across processes.
- Enforce immutable storage profiles, history/index witnesses and strict persisted-state invariants.
- Retain uncertainty after connection loss, process death or Lua errors; suppress unsafe resends.
- Share full-handler Redis coordination with verified FSM isolation and a shared Redis FSM example.
- Add real-server parity, concurrency, process-crash, ownership and recovery tests.

### Redis recovery fixes

- Preserve partial/untracked keyboards when rejecting stale callbacks.
- Fence every built-in cleanup call and skip cleanup after reentrant navigation supersedes its view.
- Count revoked handlers until cleanup completes; reject unverified FSM-isolation subclasses.
- Validate sweep namespace history and serialize scan cursors.
- Reject contradictory receipts and cross-conversation render checkpoints.
- Distinguish true NOSCRIPT responses from ambiguous transport failures and use exact server-time conversion.

### Documentation

- Align contributor guidance, typed package metadata, changelog fragments and
  repository verification tools with the related aiogram libraries.

### Miscellaneous

- Synchronize the post-commit Redis ownership-loss regression with the
  observation
  hook and protect its whole revocation sequence against cancellation, without
  relying on a 20 ms I/O deadline or incidental lease expiry under CI load.
