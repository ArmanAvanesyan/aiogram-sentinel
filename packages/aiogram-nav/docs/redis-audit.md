# Redis implementation audit

Reviewed locally on 10 November 2026 against the navigation and storage contracts.
This review changes standalone navigation only; the optional idle adapter remains
unimplemented.

## Fixes

- A stale or unknown callback previously triggered inline-markup removal from any
  non-current bot-authored message. That could strip a partially delivered view
  before its controls became active, or an unrelated application message. Rejected
  callbacks now acknowledge only. Successful navigation still cleans tracked,
  obsolete message references after commit.
- Post-commit cleanup now requires a live coordination capability and verifies
  that the committed generation is still current after observational hooks.
  Reentrant navigation cannot authorize an older operation to clean a newer view.
  `CleanupRequest.ensure_owned` is checked before every built-in cleanup API call;
  custom presenters must call it before each new external cleanup effect.
- Revoked leases remain counted as protected work until their owning scopes finish
  cleanup. Closing the repository cannot mistake revoked-but-unwinding handlers
  for a drained runtime.
- Borrowed FSM isolation requires the exact supported `SimpleEventIsolation`
  implementation. An unsafe subclass overriding its lock cannot qualify merely
  through `isinstance`. Invalid lease intervals, overflow and malformed lock
  prefixes fail before network activity.
- Sweeping validates the namespace profile, establishment witness and live-index
  sentinel atomically, including empty indexes and buffered pages. Missing
  history cannot silently appear as a successful sweep of zero records.
  Concurrent sweeps serialize their shared cursor and backlog.
- Persisted envelopes reject contradictory retention, preparation/expiry,
  completion and conversation ownership evidence. Typed cross-conversation render
  checkpoints are rejected before writing, in both memory and Redis.
- Script-cache retries recognize actual server NOSCRIPT errors. A network failure
  mentioning that text remains an uncertain mutation rather than a retry signal.
  Redis TIME converts integer microseconds directly to milliseconds.

## Regression evidence

The added tests exercise rejected callbacks during partial rendering, unrelated
keyboards, recorder reuse under successor ownership, lease loss during cleanup,
reentrant navigation after commit, revoked-handler shutdown draining, real shared
Redis FSM storage with independent clients, malformed retained receipts, concurrent
sweeps and lost transaction responses. Existing tests continue covering abrupt
process exit, partial Lua failures, unknown sends, token consumption and parity.

See [verification](verification.md) for current suite and artifact-install results.
The Redis guide documents remaining deployment limits. Leases cannot retract an
in-flight Telegram request or fence arbitrary application databases. Redis data
loss, Cluster and automatic administrative index rebuilding remain outside this
implementation.
