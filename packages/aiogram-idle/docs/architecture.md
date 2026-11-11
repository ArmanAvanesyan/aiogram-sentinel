# Architecture

An idle conversation owns an absolute session expiry and a sequence of activity
generations. Accepted activity arms a deadline according to its named policy.
Workers claim due work, inspect authorization and resumability, then use guarded
transitions to reserve prompt, resume, abandon or restore operations.

The backend commits lifecycle state, deadline changes and operation receipts
together. Memory uses a backend lock in one process. Redis uses an authoritative
record and conditional scripts with leased jobs and distributed conversation
coordination. Initialization never silently replaces established configuration.

Application callbacks and Telegram requests execute outside storage commit locks.
Effect intent is stored before a call; confirmed results are checkpointed afterward.
An interrupted call can have an unknown outcome, so recovery preserves evidence
and does not blindly resend. Leases prevent stale commits but cannot retract
in-flight requests or fence an unrelated business database.

Dispatcher integration coordinates the entire protected handler. Workers and
handlers share verified FSM isolation and the same normalized conversation lock;
disabled FSM isolation still receives package coordination. Application drafts,
authorization decisions and external database transactions remain application-owned.

The optional navigation integration stores a versioned opaque navigation component
in the idle-owned record. Accepted navigation and activity/deadline updates commit
atomically there. Navigation remains a separate package and idle core interprets
no navigation types. An FSM write or external business transaction is not included
in that atomic boundary. Read [optional navigation](navigation.md) for details.

See [recovery](recovery.md) and [Redis](redis.md) before relying on restart or
multi-process behavior. The [historical memory](audit.md) and
[Redis reviews](redis-audit.md) explain previously corrected failure paths.
