"""Real Redis validates every target before mutating canonical ledger rows."""

import json
from uuid import uuid4

import pytest

from aiogram_nav import ManualClock, NavigationConfig
from aiogram_nav.storage.ledger import LedgerRead
from aiogram_nav.storage.ledger_reducer import NavigationLedgerReducer
from aiogram_nav.storage.ledger_scripts import COMMIT
from aiogram_nav.storage.redis_ledger import commit_metadata, keys, read
from aiogram_nav.storage.redis_store import RedisStore
from aiogram_nav.storage.redis_transport import text
from tests.test_storage import KEY, enter


async def store(client):
    value = RedisStore(client, f"ledger3:{uuid4().hex}", NavigationConfig())
    await value.initialize()
    return value


async def commit(value, delta, raw=""):
    rowkeys, metadata = commit_metadata(value, KEY, getattr(delta, "canonical", delta))
    return text(
        await value.connection.script(
            COMMIT,
            [*keys(value, KEY), "unused", f"{value.prefix}:storage-format"],
            [
                value.profile,
                value.history,
                value.member(KEY),
                raw,
                json.dumps(delta.to_payload()),
                100,
                "",
                0,
                256,
                rowkeys,
                metadata,
                "{}",
                "",
            ],
        )
    )


async def initial(value):
    reducer = NavigationLedgerReducer(
        KEY,
        LedgerRead(None, None, {}, 0, {}),
        clock=ManualClock(value.clock.now()),
        config=value.config,
    )
    await enter(reducer.repository)
    return reducer.delta()


@pytest.mark.parametrize("index", [4, 5, 6, 7])
async def test_wrongtype_target_does_not_partially_write(nav_redis_client, index):
    value = await store(nav_redis_client)
    delta = await initial(value)
    targets = keys(value, KEY)
    await nav_redis_client.set(targets[index], "wrong-type")
    before = {key: await nav_redis_client.dump(key) for key in targets}
    assert await commit(value, delta) == "history"
    assert before == {key: await nav_redis_client.dump(key) for key in targets}


async def test_canonical_commit_and_selected_read_preserve_original_result(nav_redis_client):
    value = await store(nav_redis_client)
    delta = await initial(value)
    assert await commit(value, delta) == "ok"
    assert await commit(value, delta) == "retry"
    raw, reducer = await read(value, KEY, operation_id="enter")
    assert raw == delta.hot
    result = await reducer.repository.lookup_operation(KEY, operation_id="enter")
    assert result.result.snapshot.node_id == "root"
    assert reducer.read.operation_expiry["enter"] >= value.clock.now()
    assert reducer.delta().terminal_retention_ms == {}


async def test_orphan_expiry_is_typed_history_failure(nav_redis_client):
    from aiogram_nav import PersistenceUnavailable

    value = await store(nav_redis_client)
    delta = await initial(value)
    assert await commit(value, delta) == "ok"
    await nav_redis_client.zadd(keys(value, KEY)[5], {"missing": 1})
    with pytest.raises(PersistenceUnavailable):
        await read(value, KEY)


async def test_malformed_late_index_field_does_not_write_earlier_receipt(nav_redis_client):
    value = await store(nav_redis_client)
    delta = await initial(value)
    payload = delta.to_payload()
    payload["token_index_put"] = {"bad": ["not-a-string"]}

    class Malformed:
        canonical = delta

        def to_payload(self):
            return payload

    targets = keys(value, KEY)
    before = {key: await nav_redis_client.dump(key) for key in targets}
    assert await commit(value, Malformed()) == "malformed"
    assert before == {key: await nav_redis_client.dump(key) for key in targets}


async def test_terminal_receipt_physically_expires_without_polling(nav_redis_client):
    import asyncio

    from aiogram_nav.storage.redis_ledger import operation_key

    value = RedisStore(
        nav_redis_client, f"ledger3:{uuid4().hex}", NavigationConfig(recovery_seconds=0.05)
    )
    await value.initialize()
    delta = await initial(value)
    assert await commit(value, delta) == "ok"
    receipt = operation_key(value, KEY, "enter")
    assert await nav_redis_client.pttl(receipt) != -1
    await asyncio.sleep(0.08)
    assert await nav_redis_client.get(receipt) is None
    raw, reducer = await read(value, KEY, operation_id="enter")
    assert reducer.read.expired == ("enter",)
    assert (
        await reducer.repository.lookup_operation(KEY, operation_id="enter")
    ).status == "not_found"
    assert await commit(value, reducer.delta(), raw) == "ok"
    assert await nav_redis_client.hlen(keys(value, KEY)[4]) == 0


async def test_prepared_receipt_has_no_automatic_ttl(nav_redis_client):
    from aiogram_nav import NavigationIntent
    from aiogram_nav.storage.redis_ledger import operation_key

    value = await store(nav_redis_client)
    reducer = NavigationLedgerReducer(
        KEY,
        LedgerRead(None, None, {}, 0, {}),
        clock=ManualClock(value.clock.now()),
        config=value.config,
    )
    await reducer.repository.prepare(
        KEY, expected_version=None, intent=NavigationIntent("pending", "root")
    )
    assert await commit(value, reducer.delta()) == "ok"
    assert await nav_redis_client.pttl(operation_key(value, KEY, "pending")) == -1
    assert await nav_redis_client.sismember(keys(value, KEY)[7], "pending")


@pytest.mark.parametrize(
    "corruption", ["missing", "wrong-pointer", "missing-witness", "true", "1e0", "01"]
)
async def test_index_corruption_fails_closed_before_mutation(nav_redis_client, corruption):
    from aiogram_nav import PersistenceUnavailable

    value = await store(nav_redis_client)
    delta = await initial(value)
    assert await commit(value, delta) == "ok"
    targets = keys(value, KEY)
    _, original = await read(value, KEY, operation_id="enter")
    current = await original.repository.load(KEY)
    if corruption in ("missing", "wrong-pointer"):
        index = next(field for field in delta.token_index_put if field.startswith("v:"))
        if corruption == "missing":
            await nav_redis_client.hdel(targets[6], index)
        else:
            await nav_redis_client.hset(targets[6], index, "missing-owner")
    elif corruption == "missing-witness":
        await nav_redis_client.delete(targets[8])
    else:
        await nav_redis_client.set(targets[8], corruption)
    before = {key: await nav_redis_client.dump(key) for key in targets}
    with pytest.raises(PersistenceUnavailable):
        await read(value, KEY, operation_id="enter", view_id=current.snapshot.view.view_id)
    assert before == {key: await nav_redis_client.dump(key) for key in targets}


async def test_wrongtype_index_witness_prevents_all_writes(nav_redis_client):
    value = await store(nav_redis_client)
    delta = await initial(value)
    targets = keys(value, KEY)
    await nav_redis_client.hset(targets[8], "invalid", "witness")
    before = {key: await nav_redis_client.dump(key) for key in targets}
    assert await commit(value, delta) == "history"
    assert before == {key: await nav_redis_client.dump(key) for key in targets}
