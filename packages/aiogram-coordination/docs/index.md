# Shared coordination

aiogram-coordination defines task-bound scopes, distributed ownership receipts,
explicit application-owned FSM integration and read-only session authority.
It imports neither Idle nor Nav. A scope is permission to start effects during a
bounded ownership lifetime, not an exactly-once delivery guarantee.

Use the [public API](api.md), [isolation guide](isolation.md), [sessions](sessions.md)
and [Redis requirements](redis.md). Actual release preparation is described in
[releasing](releasing.md).
