# aiogram-coordination

Shared task-scoped ownership for aiogram applications and independent libraries.
The package has no dependency on aiogram-idle, aiogram-nav or aiogram-kit.

Initial alpha version: 0.1.0. Requires Python 3.10+ and aiogram 3.22–3.x.

```sh
pip install aiogram-coordination==0.1.0
# Optional renewable Redis coordination:
pip install 'aiogram-coordination[redis]==0.1.0'
```

## Memory coordination

```python
from aiogram_coordination import CoordinationKey, MemoryCoordinator

coordinator = MemoryCoordinator()
key = CoordinationKey("bot", bot_id=123, chat_id=42, user_id=42)


async def protected_operation():
    async with coordinator.hold(key):
        scope = coordinator.scope_token(key)
        assert scope is not None
        # Invoke application code only while this task owns the scope.
```

Memory scopes serialize one process and one event loop. A child task does not
inherit reentrant ownership. Identical structural conversation keys from
independent libraries normalize to one full identity; arbitrary generic Hashable
keys remain supported by the memory coordinator.

## Existing application FSM isolation

Wrap isolation explicitly when constructing the Dispatcher, not after startup:

```python
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram_coordination import TrackedEventIsolation

application_isolation = SimpleEventIsolation()
tracked = TrackedEventIsolation(application_isolation)
dispatcher = Dispatcher(events_isolation=tracked)
```

A custom application isolation requires an explicit `IsolationProvider` tied to
the exact same instance. It must return a key-bound, live `LeaseHandle` and signal
loss. Unknown opaque locks, disabled isolation and unsupported proof are rejected.
[Custom isolation](docs/isolation.md) includes the contract and Redis reference.

## Redis reference

```python
from aiogram_coordination import RenewableRedisEventIsolation, TrackedEventIsolation

# application_redis is an existing redis.asyncio client owned by your app.
application_isolation = RenewableRedisEventIsolation(redis=application_redis)
tracked = TrackedEventIsolation(application_isolation)
```

This explicit renewable provider exposes ownership; it does not pretend to renew
an opaque aiogram RedisEventIsolation lock. It reuses the caller's Redis client
and public aiogram key builder. Client closure remains application-owned.

Use `RedisCoordinator(redis=application_redis, prefix="application")` for fenced
conversation storage coordination. Its default lease/renew/wait/poll/I/O limits
are 30/10/30/0.05/5 seconds. Lost leases revoke effect authority and cancel owners.
A Lua storage transaction must check the returned fence token and positive PTTL;
a local ownership check cannot make an external API transactional.

## External sessions

`SessionAuthority.current(key)` returns an immutable `ExternalSession` or `None`.
It reads only; it never creates, extends or clears application sessions. Outages
raise `SessionAuthorityUnavailable` and are distinct from missing authorization.
[Session rules](docs/sessions.md) separate immutable absolute lifetime from a
sliding application inactivity deadline.

## Compatibility and verification

| Component | Supported / CI targets |
| --- | --- |
| Python | 3.10–3.14 |
| aiogram | 3.22 minimum and latest resolvable 3.x |
| Redis client | 5.0.8 minimum and latest below 8, optional |
| Redis server | 7+ single writable primary; CI uses real Redis 7 and 8 |
| Base install | Neither Redis nor Idle/Nav/Kit is required |

CI exercises installed wheels/sdists, task isolation, real Redis renewal/loss and
process death. [Verification evidence](reports/verification.md) distinguishes
executed checks from configured jobs. [CONTRIBUTING.md](CONTRIBUTING.md) documents
commands, [SECURITY.md](SECURITY.md) reporting and [release guidance](docs/releasing.md)
the explicit tag-only publication procedure. Nothing configures logging globally
on import. The CLI example enables only scoped development debug logging.

MIT licensed; see [LICENSE](LICENSE).
