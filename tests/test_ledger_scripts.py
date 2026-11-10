"""Real Redis validates every target before mutating canonical ledger rows."""

import json
from uuid import uuid4

import pytest

from aiogram_nav import ManualClock, NavigationConfig
from aiogram_nav.storage.ledger import LedgerRead
from aiogram_nav.storage.ledger_reducer import NavigationLedgerReducer
from aiogram_nav.storage.ledger_scripts import COMMIT
from aiogram_nav.storage.redis_ledger import keys, read
from aiogram_nav.storage.redis_store import RedisStore
from aiogram_nav.storage.redis_transport import text
from tests.test_storage import KEY, enter


async def store(client):
    value = RedisStore(client, f"ledger3:{uuid4().hex}", NavigationConfig())
    await value.initialize()
    return value


async def commit(value, delta, raw=""):
    return text(
        await value.connection.script(
            COMMIT,
            [*keys(value, KEY), "unused"],
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


@pytest.mark.parametrize("index", [4, 5, 6])
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
        def to_payload(self):
            return payload

    targets = keys(value, KEY)
    before = {key: await nav_redis_client.dump(key) for key in targets}
    assert await commit(value, Malformed()) == "malformed"
    assert before == {key: await nav_redis_client.dump(key) for key in targets}
