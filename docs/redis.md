# Redis navigation storage

The optional Redis backend persists the same navigation snapshots, prepared
operations, stage receipts and actor/session/view-bound controls as memory storage.
It is independent of aiogram-idle. No idle worker or navigation-to-idle adapter is
installed.

```sh
pip install 'aiogram-nav[redis]==0.1.0'
```

```python
from aiogram_nav import Navigation
from aiogram_nav.storage.redis import RedisNavigationRepository

repository = await RedisNavigationRepository.from_url(redis_url, prefix="my-bot:navigation")
navigation = Navigation(registry=registry, repository=repository, presenter=presenter)
# Install before business routers. Close only after handlers/workers drain.
navigation.install(dispatcher)
# ... application lifetime ...
await repository.close()
```

Alternatively supply `redis=client` and call `await repository.initialize()`.
Supplied clients remain caller-owned. `from_url` owns and closes its client.
Use a stable prefix for replicas sharing state and a separate prefix for unrelated
applications. Identity includes namespace, bot, private conversation, actor and
tenant; a shared prefix alone does not establish compatible application ownership.

## Server and configuration

Redis 7 or newer, a writable standalone primary, scripting and `noeviction` are
required. Cluster is rejected. Startup verifies these requirements and persists a
storage configuration profile. Replicas must agree on all storage limits and
lifetimes; startup never overwrites an established profile. The root node is an
application registry setting and is excluded from the storage profile.
Redis client support is `redis>=5.0.8,<8`. Operations have bounded I/O timeouts.
No failure selects a local-memory fallback.

Redis TIME supplies authoritative milliseconds. Local monotonic interpolation is
only for runtime checks between server operations. Atomic commits recheck expiry
and any coordination fence. Clock jumps are logged without exposing keys, URLs,
tokens or draft text.

The namespace stores a profile, an establishment witness, a retained-conversation
index and one versioned JSON envelope per conversation. Each mutation loads the
authoritative envelope, applies the shared memory contract as a temporary reducer,
then performs an atomic compare-and-swap. There is no persistent local mirror.
Concurrent CAS retries are bounded; stale caller versions remain conflicts.
Opaque receipts are checked before stale-version rejection. Record size is bounded
in addition to configured receipt, token, history and conversation limits.

## Ownership and FSM

A renewable Redis conversation lease serializes complete protected handlers and
navigation workers across replicas. Writes validate the lease token in the same
script as state mutation. Lease loss revokes the task capability and cancels its
owner. Copied child-task context never becomes independent lock ownership.

With `SimpleEventIsolation`, the dispatcher borrows its actual held FSM lock and
then acquires Redis. Background navigation acquires the same locks in the same
order. Disabled FSM isolation uses Redis for the entire handler. Unsupported
custom isolation is rejected. Use `FSMStrategy.USER_IN_CHAT`; for Redis FSM storage
use `DefaultKeyBuilder(with_bot_id=True)`. Every replica must use the same shared
FSM storage. A local memory FSM store remains local even when navigation is Redis.
The runnable `examples/redis_demo.py` uses a shared Redis FSM store.

A lease cannot retract an already-sent Telegram request or fence an unrelated
business database. Business writes still need their own durable version checks
and operation IDs. Navigation does not clear application FSM data.

## Recovery and operational limits

A confirmed partial render survives process exit. Retrying the original operation
reuses confirmed stage receipts and performs only definitely unsent or explicitly
safe work. An interrupted started send is uncertain; automatic resend stays
suppressed. A completed operation can be recovered without repeating delivery.
A lost commit response raises `CommitUnknown`: inspect/retry the same operation
ID before choosing a new action. Never infer that an absent receipt after Redis
data loss proves that Telegram did not receive a request.

Scripts use EVALSHA with bounded NOSCRIPT reload. Other transport failures are
uncertain execution; script errors are `BackendInconsistent`. Missing witnesses,
index inconsistencies, malformed schemas and incompatible profiles fail closed.
Do not delete or rebuild these keys while traffic runs. Corruption requires
operator investigation and explicit restoration from a consistent backup; there
is no automatic administrative index rebuild or rollback detector.

`await repository.sweep(limit=100)` walks the retained index in bounded pages and
reclaims expired terminal evidence. Unresolved operations are retained and may
exhaust capacity; inspect and resolve them instead of deleting evidence to admit
new work. Call sweep periodically if inactive conversations should be reclaimed
before the next capacity-triggered bounded sweep. There is no scheduling poller
in navigation.

Persistence, backups, replication and failover durability are deployment choices.
The package cannot recover receipts discarded by Redis rollback or total data
loss. Tests exercise real servers and process death, not infrastructure failover.

The [Redis audit](redis-audit.md) records follow-up fixes to cleanup ownership, sweep validation, strict FSM borrowing and persisted receipt validation. Rejected callbacks are acknowledgement-only; they do not prove ownership of the message containing them.
