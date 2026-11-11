"""Quiet canonical scopes retain promises and bound their recovery metadata."""

import asyncio
import json

import pytest

from aiogram_idle.errors import BackendInconsistent
from aiogram_idle.storage.canonical_gc import retirement_payload, sweep
from aiogram_idle.storage.canonical_redis import component_prefix, row_key
from tests.test_canonical_components import COMPONENT, KEY, delta, row
from tests.test_canonical_redis import create, write


async def seed(client, *, count=3, indexes=2):
    backend = await create(client)
    operations = {str(i): row(str(i), "completed") for i in range(count)}
    accepted = await write(
        backend,
        None,
        delta(
            None,
            "1",
            put=operations,
            duration={name: 50 for name in operations},
            indexes={f"t:{name}:{n}": name for name in operations for n in range(indexes)},
        ),
    )
    await asyncio.sleep(0.07)
    return backend, accepted, component_prefix(backend._store, KEY, COMPONENT)


async def due(client, backend):
    seconds, micros = await client.time()
    members = await client.zrange(backend._store.prefix + ":component-sweep", 0, -1)
    for member in members:
        await client.zadd(
            backend._store.prefix + ":component-sweep",
            {member: seconds * 1000 + micros // 1000 - 1},
        )


async def test_gc_removes_expired_rows_and_reverse_fields(redis_client):
    backend, _, prefix = await seed(redis_client)
    assert await sweep(backend._store) == 3
    assert (
        await redis_client.exists(
            prefix + ":metadata", prefix + ":indexes", prefix + ":expiry", prefix + ":protected"
        )
        == 0
    )
    assert await redis_client.zcard(backend._store.prefix + ":component-sweep") == 0
    assert await redis_client.get(prefix + ":index-count") == b"0"


async def test_gc_bounds_rows(redis_client):
    backend, _, prefix = await seed(redis_client, count=4)
    assert await sweep(backend._store, limit=2) == 2
    assert await redis_client.hlen(prefix + ":metadata") == 2
    await due(redis_client, backend)
    assert await sweep(backend._store, limit=2) == 2


async def test_gc_partially_trims_large_reverse_proof(redis_client):
    backend, _, prefix = await seed(redis_client, count=1, indexes=5)
    assert await sweep(backend._store, index_limit=2) == 0
    assert await redis_client.hlen(prefix + ":indexes") == 3
    metadata = json.loads(await redis_client.hget(prefix + ":metadata", "0"))
    assert len(metadata["index_fields"]) == 3
    await due(redis_client, backend)
    assert await sweep(backend._store, index_limit=2) == 0
    await due(redis_client, backend)
    assert await sweep(backend._store, index_limit=2) == 1


async def test_gc_wrongtype_preflights_all_deletions(redis_client):
    backend, _, prefix = await seed(redis_client)
    await redis_client.delete(prefix + ":indexes")
    await redis_client.set(prefix + ":indexes", "wrong")
    before = await redis_client.hgetall(prefix + ":metadata")
    with pytest.raises(BackendInconsistent):
        await sweep(backend._store)
    assert await redis_client.hgetall(prefix + ":metadata") == before
    assert await redis_client.zcard(prefix + ":expiry") == 3


async def test_gc_rejects_wrong_hashed_row_proof(redis_client):
    backend, _, prefix = await seed(redis_client)
    metadata = json.loads(await redis_client.hget(prefix + ":metadata", "0"))
    metadata["key"] = row_key(prefix, "foreign")
    await redis_client.hset(prefix + ":metadata", "0", json.dumps(metadata))
    with pytest.raises(BackendInconsistent):
        await sweep(backend._store)
    assert await redis_client.hlen(prefix + ":metadata") == 3


async def test_gc_keeps_current_owner_tombstone(redis_client):
    backend, accepted, prefix = await seed(redis_client, count=2)
    # Simulate the opaque hot header as the application would render it; preserve
    # the existing accepted record via the ordinary atomic component transaction.
    payload = delta("1", "2")
    state = json.loads(payload["hot"])
    state["current_owner"] = "0"
    payload["hot"] = json.dumps(state)
    from dataclasses import replace

    components = dict(accepted.components)
    components[COMPONENT] = dict(components[COMPONENT], revision="2", hot=payload["hot"])
    accepted = await backend.canonical_component_transaction(
        KEY,
        component=COMPONENT,
        expected_version=accepted.store_version,
        record=replace(accepted, components=components),
        ledger_delta=payload,
    )
    await due(redis_client, backend)
    assert await sweep(backend._store) == 1
    assert await redis_client.hexists(prefix + ":metadata", "0")
    guard = retirement_payload(backend._store, accepted, cold_key_count=6)
    assert guard is not None
    assert json.loads(guard[1])["components"][0]["current_owner"] == "0"


async def test_gc_keeps_unknown_and_promised_rows(redis_client):
    backend = await create(redis_client)
    await write(
        backend,
        None,
        delta(
            None,
            "1",
            put={"unknown": row("unknown", "unknown"), "future": row("future", "completed")},
            duration={"future": 60000},
        ),
    )
    prefix = component_prefix(backend._store, KEY, COMPONENT)
    await due(redis_client, backend)
    assert await sweep(backend._store) == 0
    assert await redis_client.sismember(prefix + ":protected", "unknown")
    assert await redis_client.hlen(prefix + ":metadata") == 2


async def guard(client, backend, record, *, deleting=True):
    from aiogram_idle.storage.canonical_gc import RETIRE_PREFLIGHT

    suffix, payload = retirement_payload(backend._store, record, cold_key_count=6)
    base = [backend._store.prefix + ":guard:" + str(n) for n in range(17)]
    base[7] = backend._store.prefix + ":expiry"
    args = [""] * 17
    args[1] = "" if deleting else "new-state"
    args[3] = backend._store.member(KEY)
    args[16] = payload
    script = (
        "local cold={gc={}};local tm=redis.call('TIME');local now=tonumber(tm[1])+tonumber(tm[2])/1000000;local nowms=math.floor(now*1000);"
        + RETIRE_PREFLIGHT
        + "return 'ok'"
    )
    return (await client.eval(script, len(base) + len(suffix), *base, *suffix, *args)).decode()


async def test_retirement_uses_server_commit_replay_not_client_hint(redis_client):
    backend = await create(redis_client)
    accepted = await write(
        backend,
        None,
        delta(None, "1", put={"one": row("one", "completed")}, duration={"one": 60000}),
    )
    before = await redis_client.get(backend._store.keys(KEY)[0])
    assert await guard(redis_client, backend, accepted) == "canonical_retained"
    assert await redis_client.get(backend._store.keys(KEY)[0]) == before
    assert (
        await redis_client.zscore(backend._store.prefix + ":expiry", backend._store.member(KEY))
        > backend.clock.now() + 50
    )
    assert await guard(redis_client, backend, accepted, deleting=False) == "ok"


async def test_retirement_preserves_unknown_indefinitely(redis_client):
    backend = await create(redis_client)
    accepted = await write(
        backend, None, delta(None, "1", put={"unknown": row("unknown", "unknown")})
    )
    assert await guard(redis_client, backend, accepted) == "canonical_retained"


async def test_retirement_wrongtype_precedes_schedule_mutation(redis_client):
    backend = await create(redis_client)
    accepted = await write(
        backend,
        None,
        delta(None, "1", put={"one": row("one", "completed")}, duration={"one": 60000}),
    )
    prefix = component_prefix(backend._store, KEY, COMPONENT)
    before = await redis_client.zscore(
        backend._store.prefix + ":expiry", backend._store.member(KEY)
    )
    await redis_client.delete(prefix + ":protected")
    await redis_client.set(prefix + ":protected", "wrong")
    from redis.exceptions import ResponseError

    with pytest.raises(ResponseError, match="retirement type"):
        await guard(redis_client, backend, accepted)
    assert (
        await redis_client.zscore(backend._store.prefix + ":expiry", backend._store.member(KEY))
        == before
    )


async def test_gc_global_index_budget_across_conversations(redis_client):
    from dataclasses import replace

    from aiogram_idle.models import IdleConversationKey

    backend, accepted, first = await seed(redis_client, count=1, indexes=5)
    other = IdleConversationKey("canonical", 1, 43, 43)
    payload = delta(
        None,
        "1",
        put={"other": row("other", "completed")},
        duration={"other": 50},
        indexes={f"t:other:{i}": "other" for i in range(5)},
    )
    await backend.canonical_component_transaction(
        other,
        component=COMPONENT,
        expected_version=None,
        record=replace(accepted, key=other),
        ledger_delta=payload,
    )
    await asyncio.sleep(0.07)
    second = component_prefix(backend._store, other, COMPONENT)
    assert await sweep(backend._store, index_limit=2) == 0
    assert (
        await redis_client.hlen(first + ":indexes") + await redis_client.hlen(second + ":indexes")
        == 8
    )


async def test_gc_index_witness_mismatch_preserves_everything(redis_client):
    backend, _, prefix = await seed(redis_client)
    await redis_client.set(prefix + ":index-count", "999")
    before = await redis_client.hgetall(prefix + ":metadata")
    with pytest.raises(BackendInconsistent):
        await sweep(backend._store)
    assert await redis_client.hgetall(prefix + ":metadata") == before
    assert await redis_client.zcard(prefix + ":expiry") == 3
