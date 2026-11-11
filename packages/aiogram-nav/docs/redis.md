# Redis navigation storage

The optional Redis backend persists the same navigation snapshots, prepared
operations, stage receipts and actor/session/view-bound controls as memory storage.
It is independent of aiogram-idle. No idle worker or navigation-to-idle adapter is
installed.

```sh
pip install 'aiogram-nav[redis]==0.3.0'
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

## Staged storage format activation (0.1 → 0.2)

New repositories write the existing format 1 by default. Version 0.2 reads formats
1 and 2, but external application-session bindings require explicit format 2.
A deployment upgrade does not automatically enable new persistence behavior.

Drain all 0.1 writers and protected handlers, take a Redis backup, and assess the
existing namespace using its exact configured prefix and storage configuration:

```python
report = await repository.activate_storage_format(operation_id="upgrade-020")
# Read-only assessment: report.before, after, conversations, pending, applied.
```

Or use the repository tool; provide credentials through the environment:

```sh
export AIOGRAM_NAV_REDIS_URL=redis://localhost:6379/0
uv run --no-sync python tools/migrate_storage.py --prefix my-navigation
uv run --no-sync python tools/migrate_storage.py --prefix my-navigation \
  --apply --old-workers-drained --operation-id upgrade-020
```

A pristine dry run does not bootstrap keys. Applying requires an explicit
operator drain assertion and zero active local coordination scopes. The CLI uses
default storage settings and strict deployment probes; deployments with customized
settings or managed-service attestation should use the API on their configured
repository. The API call is:

```python
report = await repository.activate_storage_format(
    expected=1,
    target=2,
    operation_id="upgrade-020",
    old_workers_drained=True,
    dry_run=False,
)
```

Activation atomically rotates the namespace profile/history witness and records a
stable operation receipt. An initialized old writer then fails its existing Lua
history check; an old startup fails the profile check. A lost activation response
can be retried with the same operation ID. Other operation IDs cannot silently
replace the activation decision.

Existing records, session IDs, prompt/control tokens, partial renders and operation
receipts are not rewritten or discarded by activation. New writes migrate an
individual envelope under the normal guarded transaction. Unresolved effects are
retained and are never replayed by migration. New readers accept retained format-1
records while writing format 2. Missing or corrupt format metadata fails closed.

Before activation, binary rollback is possible while format 1 remains in use.
After activation, old binaries cannot share the namespace. Use a compatible forward
fix, or a coordinated backup restore after all writers stop. Restoring a backup
cannot undo Telegram sends or application database effects; review retained
uncertainty before restarting any delivery.

## Managed Redis with denied introspection

Strict startup probes `INFO server`, `ROLE`, `INFO cluster` and
`CONFIG GET maxmemory-policy`. Supported storage is Redis 7+, a writable single
primary, non-cluster, with `noeviction`. Runtime ACLs also need `GET`, `SET`, `DEL`,
`EXISTS`, `TYPE`, `TIME`, `PTTL`, `PEXPIRE`, `SADD`, `SREM`, `SCARD`, `SISMEMBER`,
`SSCAN`, `EVALSHA` and `SCRIPT LOAD`, restricted to the chosen namespace. The Lua
scripts call the corresponding allowed data commands. Tests may use administrative
commands to create isolated ACL users; those are not runtime requirements.

If managed Redis denies introspection with `NOPERM`, supply facts independently
verified by the operator:

```python
from aiogram_nav.storage.deployment import RedisDeploymentAttestation
from aiogram_nav.storage.redis import RedisNavigationRepository

repository = RedisNavigationRepository(
    redis=application_redis,
    prefix="my-navigation",
    deployment=RedisDeploymentAttestation(
        server_major=7,
        writable_primary=True,
        cluster_enabled=False,
        maxmemory_policy="noeviction",
        operator_reference="reviewed-redis-change-123",
    ),
)
```

Attestation substitutes only the specific facts whose probe is denied. Observed
unsafe configuration, malformed responses, connection errors and timeouts still
fail startup. The library logs command names when attestation is used, not
credentials or the operator reference. There is no warning-only unsafe mode and
no memory fallback. Caller-supplied Redis clients remain caller-owned; `from_url`
creates a client closed by repository shutdown.

Redis persistence, replication and failover configuration remain deployment-owned.
A successful commit is not a guarantee against infrastructure data loss; retained
history detects missing state rather than silently reconstructing it around
uncertain Telegram effects.
