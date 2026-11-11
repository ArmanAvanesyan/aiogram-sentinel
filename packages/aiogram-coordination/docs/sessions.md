# Read-only session authority

Implement `SessionAuthority.current(CoordinationKey)` as an async read returning
`ExternalSession` or `None`. None means the application currently authorizes no
session. Transport/storage failures must raise `SessionAuthorityUnavailable`;
they must not be converted to logout, draft deletion or a new local session.

`ExternalSession(session_id, revision, absolute_expires_at, idle_expires_at=None)`
uses positive, bounded UTC epoch milliseconds. `expires_at` is the effective
minimum of absolute and optional inactivity expiry. `is_live(now_ms)` is strict:
the session is no longer live at the expiry instant.

Session IDs and opaque revision strings contain 1–256 characters. Absolute
expiry cannot change under the same session ID. The application must never reuse
an ID; receiving libraries must retain retired-session evidence for their
supported recovery window. `validate_session_transition(previous, current)`
checks immutable absolute expiry for an unchanged ID. This stateless helper
cannot prove that an application has never reused an ID in older history.

A changed inactivity deadline can be represented by a new revision while
absolute lifetime stays unchanged. Clamp an application's inactivity deadline to
absolute expiry when constructing the snapshot. Never extend authentication to
complete a promised UI grace period. Receiving libraries revalidate before new
controls/business effects and maintain their own generation-bound recovery data.
This package does not open/replace application sessions or clear FSM state.

A read-only contract does not make an independent session database and a Redis
mutation atomic. Session writes and coordinated business effects remain the
application's responsibility.
