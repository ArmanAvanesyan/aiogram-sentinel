"""Canonical rows and activity hot state commit through one fenced Redis script."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest

from aiogram_idle.errors import BackendInconsistent
from aiogram_idle.models import RuntimeSnapshot, SessionSnapshot
from aiogram_idle.storage.canonical_redis import component_prefix, row_key
from aiogram_idle.storage.redis import RedisIdleBackend
from tests.test_canonical_components import COMPONENT, IDENTITY, KEY, delta, hot, row


async def create(client):
    backend = RedisIdleBackend(
        redis=client, prefix="test:canonical:" + uuid4().hex, storage_format=3
    )
    await backend.initialize()
    return backend


async def write(backend, previous, payload):
    components = {
        COMPONENT: {
            "canonical": True,
            "revision": payload["revision"],
            "hot": hot(payload["revision"]),
            "identity": IDENTITY,
        },
        "__idle_owner__": {
            "component": COMPONENT,
            "pending": False,
            "retain_until": backend.clock.now() + 100,
        },
    }
    record = (
        replace(previous, components=components)
        if previous
        else RuntimeSnapshot(
            KEY, SessionSnapshot("session", backend.clock.now() + 100), components=components
        )
    )
    return await backend.canonical_component_transaction(
        KEY,
        component=COMPONENT,
        expected_version=previous.store_version if previous else None,
        record=record,
        ledger_delta=payload,
    )


async def test_physical_row_and_hot_commit_together_no_generic_ack(redis_client):
    backend = await create(redis_client)
    accepted = await write(backend, None, delta(None, "1", put={"one": row("one", "prepared")}))
    read = await backend.canonical_component_read(KEY, component=COMPONENT, operation_id="one")
    assert read["operations"] == {"one": row("one", "prepared")}
    prefix = component_prefix(backend._store, KEY, COMPONENT)
    assert await redis_client.pttl(row_key(prefix, "one")) == -1
    assert (
        await redis_client.exists(
            backend._store.prefix + ":receipt-index:" + backend._store.ident(KEY)
        )
        == 0
    )
    accepted = await write(
        backend,
        accepted,
        delta("1", "2", put={"one": row("one", "completed")}, duration={"one": 1000}),
    )
    expiry = await redis_client.zscore(prefix + ":expiry", "one")
    ttl = await redis_client.execute_command("PEXPIRETIME", row_key(prefix, "one"))
    assert expiry == ttl
    await asyncio.sleep(0.03)
    accepted = await write(backend, accepted, delta("2", "3", put={"one": row("one", "completed")}))
    assert await redis_client.execute_command("PEXPIRETIME", row_key(prefix, "one")) == ttl
    assert accepted.components[COMPONENT]["revision"] == "3"


async def test_suffix_wrongtype_has_no_partial_hot_or_row_write(redis_client):
    backend = await create(redis_client)
    accepted = await write(backend, None, delta(None, "1", put={"one": row("one", "prepared")}))
    prefix = component_prefix(backend._store, KEY, COMPONENT)
    before = await redis_client.get(backend._store.keys(KEY)[0])
    await redis_client.delete(prefix + ":indexes")
    await redis_client.set(prefix + ":indexes", "wrong")
    with pytest.raises(BackendInconsistent):
        await write(backend, accepted, delta("1", "2", put={"two": row("two", "prepared")}))
    assert await redis_client.get(backend._store.keys(KEY)[0]) == before
    assert await redis_client.exists(row_key(prefix, "two")) == 0


async def test_corrupt_reverse_index_race_rejects_before_all_hot_writes(redis_client):
    import hashlib

    from aiogram_idle.storage.canonical_scripts import commit_script

    class CorruptAfterObservation:
        def __init__(self):
            self.armed = False
            self.before = None

        async def execute_command(self, *args):
            digest = hashlib.sha1(commit_script().encode(), usedforsecurity=False).hexdigest()
            if self.armed and args[0] == "EVALSHA" and args[1] == digest:
                self.armed = False
                raw = json.loads(await redis_client.hget(prefix + ":metadata", "one"))
                raw["index_fields"] = 7
                await redis_client.hset(prefix + ":metadata", "one", json.dumps(raw))
                self.before = await snapshot()
            return await redis_client.execute_command(*args)

    async def snapshot():
        values = {}
        async for key in redis_client.scan_iter(match=backend._store.prefix + ":*"):
            dumped = await redis_client.dump(key)
            if dumped is not None:
                values[key] = dumped
        return values

    client = CorruptAfterObservation()
    backend = await create(client)
    prefix = component_prefix(backend._store, KEY, COMPONENT)
    accepted = await write(
        backend, None, delta(None, "1", put={"one": row("one", "completed")}, duration={"one": 5})
    )
    await asyncio.sleep(0.01)
    client.armed = True
    with pytest.raises(BackendInconsistent):
        await write(
            backend, accepted, delta("1", "2", delete=["one"], put={"two": row("two", "prepared")})
        )
    assert client.before is not None
    assert await snapshot() == client.before
    assert await redis_client.get(row_key(prefix, "two")) is None


async def test_lost_index_hash_fails_closed_with_count_witness(redis_client):
    backend = await create(redis_client)
    payload = delta(None, "1", put={"one": row("one", "prepared")})
    payload["token_index_put"] = {"v:retained": "one"}
    await write(backend, None, payload)
    prefix = component_prefix(backend._store, KEY, COMPONENT)
    assert await redis_client.get(prefix + ":index-count") == b"1"
    await redis_client.delete(prefix + ":indexes")
    with pytest.raises(BackendInconsistent):
        await backend.canonical_component_read(KEY, component=COMPONENT)


async def test_requested_expired_index_owner_beyond_gc_batch_is_classified(redis_client):
    backend = await create(redis_client)
    names = [f"op{index:02}" for index in range(40)]
    await write(
        backend,
        None,
        delta(
            None,
            "1",
            put={name: row(name, "completed") for name in names},
            duration={name: 100 for name in names},
            indexes={"v:explicit": "op39"},
        ),
    )
    await asyncio.sleep(0.15)
    result = await backend.canonical_component_read(
        KEY, component=COMPONENT, index_keys=("v:explicit",)
    )
    assert "op39" in result["expired"]
    assert len(result["expired"]) == 33
    assert result["indexes"] == {"v:explicit": "op39"}
    assert result["operations"] == {}
