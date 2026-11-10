"""Real Redis lease coordination, separate clients and task capabilities."""

import asyncio
import uuid

import pytest

from aiogram_nav.errors import OwnershipLost
from aiogram_nav.models import ConversationKey
from aiogram_nav.storage.redis_coordinator import RedisCoordinator


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
async def test_distinct_clients_serialize_and_renew(nav_redis_client, nav_redis_url):
    from redis.asyncio import Redis

    other = Redis.from_url(nav_redis_url)
    prefix = f"test-coord:{uuid.uuid4().hex}"
    first, second = coordinator(nav_redis_client, prefix), coordinator(other, prefix)
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
async def test_token_loss_revokes_effect_scope_and_preserves_successor(nav_redis_client):
    coord = coordinator(nav_redis_client, f"test-coord:{uuid.uuid4().hex}")
    key = ConversationKey("test", 1, 2, 2)
    scope = None
    with pytest.raises(OwnershipLost):
        async with coord.hold(key):
            scope = coord.scope_token(key)
            await nav_redis_client.set(coord.lock_key(key), "successor", px=1000)
            await asyncio.sleep(1)
    assert scope is not None and not coord.scope_active(scope)
    assert await nav_redis_client.get(coord.lock_key(key)) in ("successor", b"successor")
    await nav_redis_client.delete(coord.lock_key(key))


@pytest.mark.asyncio
async def test_expired_crashed_owner_is_recovered(nav_redis_client):
    coord = coordinator(nav_redis_client, f"test-coord:{uuid.uuid4().hex}")
    key = ConversationKey("test", 1, 2, 2)
    # Models a killed process: no renewer and no finally/release execution.
    await nav_redis_client.set(coord.lock_key(key), "dead-process", px=40)
    async with coord.hold(key):
        assert coord.scope_token(key) is not None
    assert await nav_redis_client.get(coord.lock_key(key)) is None


@pytest.mark.asyncio
async def test_reentrancy_is_task_scoped_and_full_identity_isolated(nav_redis_client):
    coord = coordinator(nav_redis_client, f"test-coord:{uuid.uuid4().hex}")
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
async def test_cancelled_waiter_does_not_release_owner(nav_redis_client):
    prefix = f"test-coord:{uuid.uuid4().hex}"
    first, second = coordinator(nav_redis_client, prefix), coordinator(nav_redis_client, prefix)
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
        assert await nav_redis_client.get(first.lock_key(key)) is not None
        assert second.active_scopes == 0


@pytest.mark.asyncio
async def test_renewal_io_failure_revokes_scope(nav_redis_client):
    class FailingRenewal:
        async def execute_command(self, *args):
            if args[0] == "EVAL" and "PEXPIRE" in args[1]:
                raise ConnectionError("unavailable")
            return await nav_redis_client.execute_command(*args)

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
async def test_bounded_acquisition_and_application_timeout(nav_redis_client):
    coord = RedisCoordinator(
        redis=nav_redis_client, prefix=f"test-coord:{uuid.uuid4().hex}", wait_seconds=0.03
    )
    key = ConversationKey("test", 1, 2, 2)
    await nav_redis_client.set(coord.lock_key(key), "other", px=1000)
    with pytest.raises(OwnershipLost):
        async with coord.hold(key):
            pytest.fail("occupied lock entered")
    assert coord.active_scopes == 0
    assert await nav_redis_client.get(coord.lock_key(key)) in ("other", b"other")
    await nav_redis_client.delete(coord.lock_key(key))
    with pytest.raises(TimeoutError, match="application"):
        async with coord.hold(key):
            raise TimeoutError("application")


@pytest.mark.asyncio
async def test_verified_fsm_borrow_and_worker_use_same_local_lock(nav_redis_client):
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import SimpleEventIsolation

    coord = coordinator(nav_redis_client, f"test-coord:{uuid.uuid4().hex}")
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
async def test_delegated_fence_is_bound_to_live_conversation(nav_redis_client):
    coord = coordinator(nav_redis_client, f"test-coord:{uuid.uuid4().hex}")
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
async def test_external_cancellation_preserved_and_owner_releases(nav_redis_client):
    coord = coordinator(nav_redis_client, f"test-coord:{uuid.uuid4().hex}")
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
    assert await nav_redis_client.get(coord.lock_key(key)) is None
