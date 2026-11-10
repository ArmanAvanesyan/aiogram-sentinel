# Redis storage

Install the optional Redis client dependency:

```sh
python -m pip install 'aiogram-idle[redis]==0.1.0'
```

Use a writable, standalone Redis 7+ primary configured with
`maxmemory-policy noeviction`. Startup verifies the server version, role, cluster
mode and eviction policy, so the connection must be authorized for `INFO`, `ROLE`
and `CONFIG GET` as well as the backend data and scripting commands. Redis
Cluster is currently rejected.

In managed environments, denied introspection requires an explicit operator
attestation rather than a general "skip checks" switch:

```python
from aiogram_idle import RedisDeploymentAttestation
from aiogram_idle.storage.redis import RedisIdleBackend

deployment = RedisDeploymentAttestation(
    server_major=7,
    writable_primary=True,
    cluster_enabled=False,
    maxmemory_policy="noeviction",
    operator_reference="reviewed infrastructure change identifier",
)
backend = RedisIdleBackend(redis=redis, prefix="my-bot:idle", deployment=deployment)
```

The library still attempts each inspection. Only a Redis ACL permission denial
permits the corresponding attested fact to be substituted. Connection failures,
malformed responses and observed unsafe facts still fail closed. The reference
records which infrastructure configuration was reviewed; it must not contain a
credential. A new primary or infrastructure change requires the operator to
recheck these facts. Actual writes and Lua scripts must still be permitted.

## Redis ACL and durability

The backend requires `TIME`, `GET`, `SET`, `DEL`, `EXISTS`, `TYPE`, `PTTL`,
`PEXPIRE`, `EVAL`, `EVALSHA`, `SCRIPT LOAD`, `SADD`, `SREM`, `SCARD`,
`SISMEMBER`, `SSCAN`, `SCAN`, `HGET`, `HSET`, `HDEL`, `HEXISTS`, `HLEN`,
`HSCAN`, `ZADD`, `ZREM`, `ZCARD`, `ZRANGE` and `ZRANGEBYSCORE` for its namespace,
including conversation locks. Lua execution needs permission for its constituent
commands. Strict deployment checks also require `INFO server`, `INFO cluster`,
`ROLE` and `CONFIG GET maxmemory-policy`. Administrative ACL creation/deletion
belongs to the operator, not the backend.

Configure persistence and replication for the application's durability needs.
`noeviction` prevents memory-pressure eviction; it does not guarantee that a
crashed primary's last acknowledged writes survive failover. There is no Redis
Cluster support or memory fallback. Caller-supplied clients remain caller-owned;
`from_url` creates a client closed by the backend.

## Staged 0.1 to 0.2 storage activation

Version 0.2 reads envelope formats 1 and 2, but continues writing format 1 until
explicit activation. External application-session binding requires format 2.
Conversation identity encoding and Redis key names never change.

Roll out 0.2 in compatibility mode first. Stop idle pollers, drain protected
handlers and remove every 0.1 writer before activation. Take a Redis backup, then
initialize a 0.2 backend and assess the namespace:

```python
report = await backend.activate_storage_format(operation_id="upgrade-0.2")
assert report.dry_run
await backend.activate_storage_format(
    operation_id="upgrade-0.2", old_workers_drained=True, dry_run=False
)
```

Activation refuses active claims or local scopes. It atomically records the
stable operation ID and rotates the namespace profile/history, preserving the
original creation timestamp. Existing 0.1 writers lose their old history fence;
0.1 startup cannot accept the new profile. Reopen all other backend instances
after activation. A lost activation response can be retried with the same ID;
another ID cannot silently claim that administrative operation. Repeated Redis
activation returns `changed=False` with unassessed statistics set to `None`, not
a false claim that the namespace contains zero records.

Activation does not rewrite or delete conversations, claims, policies or operation
receipts. Format-1 records are rewritten to format 2 on their next normal CAS
mutation. A bounded administrative pass can assess or convert dormant records:

```python
page = await backend.migrate_storage_records(cursor="0", limit=100)
page = await backend.migrate_storage_records(cursor="0", limit=100, dry_run=False)
# Continue with page.cursor until it is "0". Repeated pages are safe.
```

Migration preserves uncertain effects, control tokens, receipts and deadlines;
it invokes no presenter, business callback or Telegram API. The corresponding
`tools/storage_format.py` command reads `AIOGRAM_IDLE_REDIS_URL` from the
environment and defaults to assessment. Run `--help` for activation, bounded
migration and optional attestation-file arguments.

Before activation, binaries may be rolled back without format migration. After
activation, do not run 0.1 against that namespace. Use a compatible forward fix
or a coordinated restore from the pre-activation backup; never erase unresolved
effect evidence to make a downgrade start.

The Redis backend implements the same idle-owned session, activity, control-token,
operation receipt and deadline contracts as memory storage. It does not depend on
`aiogram-nav`. Applications can use commands, reply keyboards, inline keyboards,
or hybrid prompt controls with either backend.

```python
from redis.asyncio import Redis
from aiogram_idle.storage.redis import RedisIdleBackend

redis = Redis.from_url("redis://localhost:6379/0")
backend = RedisIdleBackend(redis=redis, prefix="my-bot:idle")
await backend.initialize()
# Supply backend to IdleRuntime with your policies, adapters and presenter.
# On shutdown: stop the runtime, close backend, then close your Redis client.
await backend.close()
await redis.aclose()
```

Use one stable, application-specific prefix across replicas. Separate environments
and independent bot applications should have different prefixes. Reusing a prefix
also reuses its configuration manifest; initialization never implicitly changes an
existing enabled flag or policy digest. Administrative configuration changes use
an expected manifest generation and an operation ID.

## Ownership and concurrency

Every replica polls the shared deadline queue. Claims have random owner tokens,
generations and expiration times. Claim, renew and completion are conditional:
a late worker cannot complete another worker's claim or remove a newer activity's
deadline. Logical deadlines and lease comparisons use Redis server time.

The distributed conversation coordinator serializes protected handlers and idle
workers. Every participant that changes the application's conversation state must
use the same coordination domain. The coordination scope is task-scoped; a child
task cannot borrow its parent's ownership. Lease loss invalidates the scope.
aiogram's `SimpleEventIsolation` and disabled isolation are supported while the
Redis coordinator remains the outer lock for both handlers and workers. A custom
`RedisEventIsolation` is rejected rather than borrowed: an independently configured
FSM lock does not establish shared idle ownership. Application draft persistence
is still the application's responsibility. Using aiogram `MemoryStorage` keeps FSM
drafts process-local and non-durable even when idle records are stored in Redis.

Atomic state commits also maintain deadline indexes. The local domain reducer does
not act as a fallback store: Redis remains authoritative. Application callbacks,
Telegram requests and other network effects run outside storage commit operations.

## Failures and recovery

- A process dying after claiming leaves a leased job. Another replica can reclaim
  it when the lease expires; taking the job does not delete its recovery evidence.
- Recorded effect intent precedes external delivery or business actions. Confirmed
  receipts survive reconstruction and prevent those effects from being repeated.
- An uncertain network result is not evidence of failure. The default policy keeps
  ambiguous delivery or adapter effects explicit and suppresses blind resend.
  Applications must reconcile uncertain outcomes using their own idempotency keys
  and external evidence where available.
- If a Redis response is lost during mutation, the operation ID and canonical
  fingerprint allow lookup and deduplicated retry. A successful remote commit may
  have occurred even when the caller did not receive its response.
- Redis unavailability fails closed. There is no automatic memory fallback. Do not
  catch persistence failures and execute the application action without ownership.
- Redis script-cache eviction is recoverable: scripts are reloaded after `NOSCRIPT`.
  Index reconciliation is bounded; it does not authorize an external effect replay.
- Missing or incompatible authoritative records must be investigated, rather than
  silently resetting the conversation and issuing a new prompt.

Redis durability is a deployment responsibility. Configure persistence, backups,
access controls and eviction to preserve authoritative records. A cache configured
to evict arbitrary keys cannot provide the library's recovery guarantees. Retention
must cover the required recovery horizon; it is not a durable analytics outbox.
Exactly-once Telegram delivery is not guaranteed when the transport outcome is
unknown. Navigation adapters and external session stores remain separate concerns.

## Real-server tests

Use a disposable Redis server, never a production database. Tests generate unique
prefixes and do not run `FLUSHALL` or `FLUSHDB`. The script-cache recovery test does
run `SCRIPT FLUSH`, so its server must be dedicated to this test run.

```sh
AIOGRAM_IDLE_REDIS_URL=redis://127.0.0.1:6379/0 \
AIOGRAM_IDLE_REQUIRE_REDIS=1 \
uv run --no-sync pytest tests/test_redis_backend.py tests/test_redis_recovery.py
```

The suite covers shared memory/Redis domain contracts, concurrent workers, expired
leases, stale ownership, a process killed after claim acquisition, confirmed and
uncertain delivery recovery, and loss of the Lua script cache. Redis tests can be
skipped locally when no server URL is supplied. Required CI runs set
`AIOGRAM_IDLE_REQUIRE_REDIS=1`, making a missing server configuration an error.

## Explicit index recovery

Normal `reconcile(limit=100)` follows retained membership and repairs missing due
entries without replaying effects. If membership itself was lost, an operator can
explicitly scan this backend's authoritative records:

```python
while True:
    page = await backend.recover_indexes(limit=100)
    if page.complete:
        break
```

Each call processes a bounded page and buffers scan overflow. Successful CAS
commits reconstruct membership, expiry, routing and deadline indexes while
preserving live claims. This cannot reconstruct a missing authoritative record,
lost receipts, business drafts or effects after Redis data loss. Corrupt records
raise a typed error and require investigation. Run administrative recovery from
one task, against the intended application prefix.

A persisted disarm epoch prevents an old active deadline from resurfacing after
an administrative disable/re-enable, even when background reconciliation has not
visited that conversation. Explicitly accepted new activity can arm it again.

Unsupported schemas and corrupt conversations encountered by polling are parked
separately, preserving their authoritative record and job evidence while healthy
conversations continue. `inspect_parked(cursor=0, limit=100)` returns safe reason
codes. After an operator resolves the schema/evidence problem,
`release_parked(key)` validates it before restoring scheduling. Release does not
confirm or replay an unknown external effect.


## Reviewed concurrency requirements

The [follow-up audit](redis-audit.md) records the corrected races and recovery
contracts. All replicas using one prefix must agree on retention and storage
capacities. The namespace profile rejects incompatible clients; an older layout
without this profile requires explicit migration rather than automatic rewriting.
Established configuration loss is an error, never a request to bootstrap defaults.

For aiogram RedisStorage, configure a lossless builder such as
`DefaultKeyBuilder(prefix="my-bot:fsm", with_bot_id=True)`. The default builder
without bot identity is rejected by distributed integration. When using
SimpleEventIsolation, workers and updates share its exact instance and acquire
it before the distributed lock. Keep FSM middleware and isolation unchanged after
installation. Disabled FSM isolation is protected by the distributed coordinator.

Retained EFFECT_UNKNOWN or QUARANTINED business operations block ordinary handlers
and public activity replacement until trusted recovery resolves the outcome.
Do not use clear/enter/touch to discard that evidence. DELIVERY_UNKNOWN still
supports its separately documented ordinary-activity supersession behavior.
