# Changelog

<!-- towncrier release notes start -->

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
