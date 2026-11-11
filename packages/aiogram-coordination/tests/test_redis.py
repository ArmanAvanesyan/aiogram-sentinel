"""Real Redis lease coordination, separate clients and task capabilities."""

import asyncio
import uuid

import pytest

from aiogram_coordination import CoordinationKey as ConversationKey
from aiogram_coordination import OwnershipLost, RedisCoordinator


def coordinator(client, prefix):
    return RedisCoordinator(
        redis=client,
        prefix=prefix,
        lease_seconds=0.3,
        renew_seconds=0.05,
        wait_seconds=1,
        poll_seconds=0.005,
        io_timeout=0.1,
    )


@pytest.mark.asyncio
async def test_distinct_clients_serialize_and_renew(redis_client, redis_url):
    from redis.asyncio import Redis

    other = Redis.from_url(redis_url)
    prefix = f"test-coord:{uuid.uuid4().hex}"
    first, second = coordinator(redis_client, prefix), coordinator(other, prefix)
    key = ConversationKey("test", 1, 2, 2)
    entered = asyncio.Event()
    release = asyncio.Event()
    order = []

    async def owner():
        async with first.hold(key):
            order.append("first")
            entered.set()
            await release.wait()

    async def waiter():
        async with second.hold(key):
            order.append("second")

    task = asyncio.create_task(owner())
    await entered.wait()
    waiting = asyncio.create_task(waiter())
    await asyncio.sleep(0.4)  # longer than the original lease
    assert order == ["first"]
    assert second.active_scopes == 1
    release.set()
    await asyncio.gather(task, waiting)
    assert order == ["first", "second"]
    assert first.active_scopes == second.active_scopes == 0
    await other.aclose()


@pytest.mark.asyncio
async def test_token_loss_revokes_effect_scope_and_preserves_successor(redis_client):
    coord = coordinator(redis_client, f"test-coord:{uuid.uuid4().hex}")
    key = ConversationKey("test", 1, 2, 2)
    scope = None
    with pytest.raises(OwnershipLost):
        async with coord.hold(key):
            scope = coord.scope_token(key)
            await redis_client.set(coord.lock_key(key), "successor", px=1000)
            await asyncio.sleep(1)
    assert scope is not None and not coord.scope_active(scope)
    assert await redis_client.get(coord.lock_key(key)) in ("successor", b"successor")
    await redis_client.delete(coord.lock_key(key))


@pytest.mark.asyncio
async def test_expired_crashed_owner_is_recovered(redis_client):
    coord = coordinator(redis_client, f"test-coord:{uuid.uuid4().hex}")
    key = ConversationKey("test", 1, 2, 2)
    # Models a killed process: no renewer and no finally/release execution.
    await redis_client.set(coord.lock_key(key), "dead-process", px=40)
    async with coord.hold(key):
        assert coord.scope_token(key) is not None
    assert await redis_client.get(coord.lock_key(key)) is None


@pytest.mark.asyncio
async def test_reentrancy_is_task_scoped_and_full_identity_isolated(redis_client):
    coord = coordinator(redis_client, f"test-coord:{uuid.uuid4().hex}")
    key = ConversationKey("test", 1, 2, 2)
    async with coord.hold(key):
        token = coord.scope_token(key)
        fence = coord.fencing(key)
        assert fence is not None and fence[0] == coord.lock_key(key)
        async with coord.hold(key):
            assert coord.scope_token(key) is token

        async def child():
            assert coord.scope_token(key) is None
            assert coord.fencing(key) is None

        await asyncio.create_task(child())
        async with coord.hold(ConversationKey("test", 1, 2, 2, tenant_id="other")):
            assert coord.active_scopes == 2
    assert token is not None and not coord.scope_active(token)
    assert coord.fencing(key) is None


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_release_owner(redis_client):
    prefix = f"test-coord:{uuid.uuid4().hex}"
    first, second = coordinator(redis_client, prefix), coordinator(redis_client, prefix)
    key = ConversationKey("test", 1, 2, 2)
    async with first.hold(key):

        async def waiter():
            async with second.hold(key):
                pytest.fail("waiter entered occupied lock")

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await redis_client.get(first.lock_key(key)) is not None
        assert second.active_scopes == 0


@pytest.mark.asyncio
async def test_renewal_io_failure_revokes_scope(redis_client):
    class FailingRenewal:
        async def execute_command(self, *args):
            if args[0] == "EVAL" and "PEXPIRE" in args[1]:
                raise ConnectionError("unavailable")
            return await redis_client.execute_command(*args)

    coord = coordinator(FailingRenewal(), f"test-coord:{uuid.uuid4().hex}")
    key = ConversationKey("test", 1, 2, 2)
    scope = None
    with pytest.raises(OwnershipLost):
        async with coord.hold(key):
            scope = coord.scope_token(key)
            await asyncio.sleep(1)
    assert scope is not None and not coord.scope_active(scope)
    assert coord.active_scopes == 0


@pytest.mark.asyncio
async def test_bounded_acquisition_and_application_timeout(redis_client):
    coord = RedisCoordinator(
        redis=redis_client, prefix=f"test-coord:{uuid.uuid4().hex}", wait_seconds=0.03
    )
    key = ConversationKey("test", 1, 2, 2)
    await redis_client.set(coord.lock_key(key), "other", px=1000)
    with pytest.raises(OwnershipLost):
        async with coord.hold(key):
            pytest.fail("occupied lock entered")
    assert coord.active_scopes == 0
    assert await redis_client.get(coord.lock_key(key)) in ("other", b"other")
    await redis_client.delete(coord.lock_key(key))
    with pytest.raises(TimeoutError, match="application"):
        async with coord.hold(key):
            raise TimeoutError("application")


@pytest.mark.asyncio
async def test_verified_fsm_borrow_and_worker_use_same_local_lock(redis_client):
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import SimpleEventIsolation

    coord = coordinator(redis_client, f"test-coord:{uuid.uuid4().hex}")
    isolation = SimpleEventIsolation()
    coord.configure_fsm_isolation(isolation)
    key = ConversationKey("test", 1, 2, 2)
    storage_key = StorageKey(bot_id=1, chat_id=2, user_id=2)
    entered = asyncio.Event()

    async def worker():
        async with coord.hold(key):
            entered.set()

    async with isolation.lock(key=storage_key):
        async with coord.borrowed_fsm(key):
            assert coord.fencing(key) is not None
            task = asyncio.create_task(worker())
            await asyncio.sleep(0.02)
            assert not entered.is_set()
            assert coord.active_scopes == 2
    await task
    assert entered.is_set()
    assert coord.active_scopes == 0
    await isolation.close()


@pytest.mark.asyncio
async def test_delegated_fence_is_bound_to_live_conversation(redis_client):
    coord = coordinator(redis_client, f"test-coord:{uuid.uuid4().hex}")
    key = ConversationKey("test", 1, 2, 2)
    async with coord.hold(key):
        scope = coord.scope_token(key)
        assert scope is not None

        async def checkpoint():
            assert coord.fencing(key) is None
            assert coord.fencing(key, scope=scope) is not None
            with pytest.raises(OwnershipLost):
                coord.fencing(ConversationKey("different", 1, 2, 2), scope=scope)

        await asyncio.create_task(checkpoint())
    with pytest.raises(OwnershipLost):
        coord.fencing(key, scope=scope)


@pytest.mark.asyncio
async def test_external_cancellation_preserved_and_owner_releases(redis_client):
    coord = coordinator(redis_client, f"test-coord:{uuid.uuid4().hex}")
    key = ConversationKey("test", 1, 2, 2)
    entered = asyncio.Event()
    observed = []

    async def owner():
        try:
            async with coord.hold(key):
                entered.set()
                await asyncio.Event().wait()
        except asyncio.CancelledError as error:
            observed.append(error.args)
            raise

    task = asyncio.create_task(owner())
    await entered.wait()
    task.cancel("external")
    with pytest.raises(asyncio.CancelledError):
        await task
    # CPython 3.10 may discard the message when awaiting a cancelled Task;
    # verify provenance inside the owner, where the coordinator propagates it.
    assert observed == [("external",)]
    assert coord.active_scopes == 0
    assert await redis_client.get(coord.lock_key(key)) is None


async def test_structural_peer_key_reentry_preserves_fenced_scope(redis_client):
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Peer:
        namespace: str
        bot_id: int
        chat_id: int
        user_id: int
        tenant_id: str | None = None

    coord = coordinator(redis_client, "test-coord:" + uuid.uuid4().hex)
    key = ConversationKey("test", 1, 2, 2)
    other = Peer("test", 1, 2, 2)
    async with coord.hold(key):
        token = coord.scope_token(key)
        async with coord.hold(other):
            assert coord.scope_token(other) is token
            assert coord.fencing(other) == coord.fencing(key)
            assert coord.scope_matches(other, token)
            assert coord.active_scopes == 1


async def test_killed_process_loses_lease_without_releasing_successor(redis_client, redis_url):
    import os
    import sys

    prefix = "test-kill:" + uuid.uuid4().hex
    program = """import asyncio, os
from redis.asyncio import Redis
from aiogram_coordination import RedisCoordinator, CoordinationKey
async def main():
    client = Redis.from_url(os.environ['COORD_CRASH_REDIS_URL'])
    coordinator = RedisCoordinator(redis=client, prefix=os.environ['COORD_CRASH_PREFIX'], lease_seconds=.4, renew_seconds=.05, io_timeout=.1)
    async with coordinator.hold(CoordinationKey('test', 1, 2, 2)):
        print('ready', flush=True)
        await asyncio.Event().wait()
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        program,
        stdout=asyncio.subprocess.PIPE,
        env={**os.environ, "COORD_CRASH_REDIS_URL": redis_url, "COORD_CRASH_PREFIX": prefix},
    )
    try:
        assert await asyncio.wait_for(process.stdout.readline(), timeout=15) == b"ready\n"
        process.kill()
        await process.wait()
        replacement = coordinator(redis_client, prefix)
        async with replacement.hold(ConversationKey("test", 1, 2, 2)):
            assert replacement.fencing(ConversationKey("test", 1, 2, 2))
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


@pytest.mark.parametrize("release_error", [False, True])
async def test_drain_counts_token_release_tail_and_definite_failure(redis_client, release_error):
    from aiogram.fsm.storage.memory import SimpleEventIsolation

    from aiogram_coordination import ConfigurationError

    releasing, allow_release = asyncio.Event(), asyncio.Event()

    class SlowRelease:
        async def execute_command(self, *args):
            if args[0] == "EVAL" and "'DEL'" in args[1]:
                releasing.set()
                await allow_release.wait()
                if release_error:
                    raise ConnectionError("release response unavailable")
            return await redis_client.execute_command(*args)

    coord = coordinator(SlowRelease(), "tail:" + uuid.uuid4().hex)
    key = ConversationKey("test", 1, 2, 2)
    scopes = []

    async def owner():
        async with coord.hold(key):
            scopes.append(coord.scope_token(key))

    task = asyncio.create_task(owner())
    await releasing.wait()
    assert coord.active_scopes == 1
    assert not coord.scope_active(scopes[0])
    with pytest.raises(ConfigurationError):
        coord.configure_fsm_isolation(SimpleEventIsolation())
    allow_release.set()
    await task
    assert coord.active_scopes == 0
    await redis_client.delete(coord.lock_key(key))
