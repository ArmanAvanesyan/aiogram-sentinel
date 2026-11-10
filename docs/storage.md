# Memory storage and recovery

`MemoryNavigationRepository` supplies single-process storage. One
repository instance and its coordinator must serve the conversation's writers.
It is single-process, in-memory and non-durable: restarting loses snapshots,
callback tokens and render evidence. The optional [Redis backend](redis.md) persists
these contracts across processes; selecting a backend never
silently falls back to memory.

## Prepare, effect, complete

A navigation action validates its target and permission, then prepares a reserved
operation before sending anything. The old committed screen remains current while
rendering is pending. Each external stage records intent before the call and its
receipt after a confirmed response. Full rendering completes the reserved view and
commits location, history and accepted activity atomically inside the repository.

An inline send and a reply-tray send are distinct effects. If one succeeds and the
next fails, the operation retains its confirmed message references; it does not
pretend the target is fully displayed. A lost Telegram response can mean the send
happened. `RenderUnknown` prevents automatic resend of that uncertain stage.
Confirmed subeffects can be reused when the operation is retried; definite unsent
or explicitly safe stages have separate recovery semantics.

A storage response lost after rendering is also uncertain. Use the same operation
ID and lookup the recorded operation before selecting any new action. A CAS
conflict is not permission to repeat a cancellation hook or Telegram send.

## Bounds and ownership

History, conversations, operation receipts and callback tokens are bounded. Expired
terminal evidence can be swept. Admission rejects capacity exhaustion when making
space would discard unresolved recovery evidence. Retained operation IDs also
carry canonical input fingerprints: an identical retry is deduplicated before its
old CAS version is checked; a different payload is a conflict.

Full protected handlers and application hooks use task-scoped conversation
coordination. Child tasks cannot inherit lock ownership after the parent exits.
The storage lock covers atomic in-memory mutations, while application callbacks
and network requests execute outside it. No local lock makes a Telegram call and
an external business database one transaction.

## Extension boundary

The repository protocol is navigation-owned. A future optional adapter can project
it onto idle-owned component storage and atomically map navigation to accepted
idle activity. That adapter is not part of this package and no idle dependency or
unfinished integration extra is installed. Standalone navigation must remain
usable without a session-idle framework.

Active/prepared controls are bounded by max_tokens. After view replacement, old controls become inert and leave the active table; bounded per-action token receipts preserve retry fingerprints until normal action-receipt retention expires. Effect stage counts are bounded by max_receipts and individual result payloads by max_params_bytes. Admission rejects rather than discarding unresolved recovery evidence.
