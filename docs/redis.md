# Redis deployment and failure handling

Redis support is optional. Install `aiogram-coordination[redis]` when constructing
a Redis client; injecting an existing async client does not transfer ownership.
Redis client 5.0.8–7.x and Redis server 7+ are supported. Use one writable primary;
Redis Cluster and infrastructure failover durability are not qualified here.

The coordinator requires `SET` (NX/PX), `EVAL`, and the commands used by its Lua:
`GET`, `PTTL`, `PEXPIRE` and `DEL`. Limit ACL keys to the selected conversation-lock
prefix or the application's FSM lock namespace. These coordination primitives do
not require `INFO`, `ROLE` or `CONFIG`; consuming storage backends can require
additional validation and storage commands. Their stricter requirements remain
in force.

Default lease: 30 s; renewal: 10 s; acquisition wait: 30 s; poll: 50 ms; I/O: 5 s.
Renewal plus I/O must fit inside the lease. Intervals must be positive, finite and
bounded. Prefixes are bounded and cannot contain whitespace.

Conversation locks retain the canonical identity encoding
`[namespace, tenant_id, bot_id, chat_id, user_id]` and SHA256 lock suffix, so thin
Idle/Nav facades can preserve their existing prefixes during upgrades. An owner
may release only its own token. Renewal cannot resurrect an expired or replaced
lease. Crashed processes recover through expiry, not guessed local unlocks.

Redis loss raises `PersistenceUnavailable` on operations. Renewal failure revokes
scope authority and cancels its owning operation. External cancellation keeps its
provenance. No memory fallback exists. An ambiguous external send remains an
application/library recovery decision; renewal cannot undo an accepted request.

A fenced storage transaction must compare the supplied owner token and a
positive Redis PTTL atomically inside Lua. Checking only `scope_active` locally
is insufficient. Configure eviction and persistence according to the authoritative
storage library; this package alone does not provide durable application state.
