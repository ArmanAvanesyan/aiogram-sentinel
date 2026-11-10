"""Transport uncertainty must never be mistaken for a safe script-cache retry."""

from uuid import uuid4

import pytest

from aiogram_nav import CommitUnknown, NavigationIntent
from aiogram_nav.storage.redis import RedisNavigationRepository
from aiogram_nav.storage.redis_transport import Connection, RedisClock
from tests.test_redis_backend import KEY


async def test_network_failure_mentioning_noscript_does_not_retry_committed_mutation(
    nav_redis_client,
):
    class Wire:
        armed = False
        discarded = 0

        async def execute_command(self, *args):
            response = await nav_redis_client.execute_command(*args)
            if self.armed and args[0] == "EVALSHA" and args[2] == 5:
                self.discarded += 1
                raise ConnectionError("NOSCRIPT was mentioned by an intermediary")
            return response

    wire = Wire()
    repo = RedisNavigationRepository(redis=wire, prefix=f"test:review:{uuid4().hex}")
    await repo.initialize()
    # Load the real COMMIT script first so the injected failure follows execution.
    from aiogram_nav.storage.redis_scripts import COMMIT

    await nav_redis_client.script_load(COMMIT)
    wire.armed = True
    with pytest.raises(CommitUnknown):
        await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("one", "main"))
    wire.armed = False
    assert wire.discarded == 1
    assert (await repo.lookup_operation(KEY, operation_id="one")).status == "prepared"


async def test_server_time_converts_integer_microseconds_without_float_rounding():
    class TimeWire:
        async def execute_command(self, *args):
            assert args == ("TIME",)
            return [str(2**40).encode(), b"999999"]

    connection = Connection(TimeWire(), RedisClock())
    assert await connection.time() == (2**40) * 1000 + 999
