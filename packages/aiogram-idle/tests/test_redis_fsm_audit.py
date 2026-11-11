"""Audit regressions for renewable ownership and exact FSM lock sharing."""

import asyncio
from uuid import uuid4

import pytest
from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import Update

from aiogram_idle.errors import ConfigurationError, OwnershipLost
from aiogram_idle.integration import install
from aiogram_idle.storage.redis_coordinator import RedisCoordinator
from tests.test_telegram import KEY, FakeRuntime, message


async def test_revoked_open_scope_cannot_reacquire_or_make_unfenced_commit(redis_client):
    coord = RedisCoordinator(redis=redis_client, prefix=f"audit-scope:{uuid4().hex}")
    with pytest.raises(OwnershipLost):
        async with coord.hold(KEY):
            scope = coord.scope_token(KEY)
            coord._valid_until[scope] = asyncio.get_running_loop().time() - 1
            await redis_client.delete(coord.lock_key(KEY))
            with pytest.raises(OwnershipLost):
                async with coord.hold(KEY):
                    pytest.fail("expired handler acquired a new lease")
            with pytest.raises(OwnershipLost):
                coord.fencing(KEY)
            with pytest.raises(ConfigurationError):
                coord.configure_fsm_isolation(SimpleEventIsolation())
            assert await redis_client.get(coord.lock_key(KEY)) is None


async def test_captured_scope_fences_child_without_granting_lock_ownership(redis_client):
    coord = RedisCoordinator(redis=redis_client, prefix=f"audit-scope:{uuid4().hex}")
    other = type(KEY)("other", KEY.bot_id, KEY.chat_id, KEY.user_id)
    async with coord.hold(KEY):
        scope = coord.scope_token(KEY)
        fence = coord.fencing(KEY)

        async def checkpoint():
            assert coord.scope_token(KEY) is None
            assert not coord.owns(KEY)
            assert coord.fencing(KEY, scope=scope) == fence
            with pytest.raises(OwnershipLost):
                coord.fencing(other, scope=scope)

        await asyncio.create_task(checkpoint())
    with pytest.raises(OwnershipLost):
        coord.fencing(KEY, scope=scope)


async def test_worker_acquires_same_local_fsm_lock_before_distributed_lock(redis_client):
    coord = RedisCoordinator(redis=redis_client, prefix=f"audit-fsm:{uuid4().hex}")
    isolation = SimpleEventIsolation()
    coord.configure_fsm_isolation(isolation)
    entered = asyncio.Event()

    async def worker():
        async with coord.hold(KEY):
            entered.set()

    storage_key = StorageKey(bot_id=KEY.bot_id, chat_id=KEY.chat_id, user_id=KEY.user_id)
    async with isolation.lock(key=storage_key):
        task = asyncio.create_task(worker())
        await asyncio.sleep(0.03)
        assert not entered.is_set()
        assert coord.active_scopes == 1
        assert await redis_client.get(coord.lock_key(KEY)) is None
    await asyncio.wait_for(task, timeout=5)
    assert entered.is_set()
    await isolation.close()


async def test_disabled_fsm_does_not_borrow_unheld_simple_lock(redis_client):
    bot = Bot("123456:ABC")
    isolation = SimpleEventIsolation()
    dispatcher = Dispatcher(disable_fsm=True, events_isolation=isolation)
    runtime = FakeRuntime(bot)
    runtime.coordinator = RedisCoordinator(redis=redis_client, prefix=f"audit-fsm:{uuid4().hex}")
    install(runtime, dispatcher, lifecycle=False)
    called = []

    @dispatcher.message()
    async def handler(message):
        called.append(runtime.coordinator.scope_token(KEY))

    try:
        await asyncio.wait_for(
            dispatcher.feed_update(bot, Update(update_id=1, message=message())), 5
        )
        assert called and called[0] is not None
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_conflicting_fsm_lock_configuration_is_rejected(redis_client):
    bot = Bot("123456:ABC")
    runtime = FakeRuntime(bot)
    runtime.coordinator = RedisCoordinator(redis=redis_client, prefix=f"audit-fsm:{uuid4().hex}")
    first, second = (
        Dispatcher(events_isolation=SimpleEventIsolation()),
        Dispatcher(events_isolation=SimpleEventIsolation()),
    )
    try:
        install(runtime, first, lifecycle=False)
        with pytest.raises(ConfigurationError):
            install(runtime, second, lifecycle=False)
        assert not second.get("_aiogram_idle_installed")
    finally:
        await first.fsm.close()
        await second.fsm.close()
        await bot.session.close()


async def test_active_coordinator_cannot_bind_another_fsm_lock(redis_client):
    coord = RedisCoordinator(redis=redis_client, prefix=f"audit-fsm:{uuid4().hex}")
    async with coord.hold(KEY):
        with pytest.raises(ConfigurationError):
            coord.configure_fsm_isolation(SimpleEventIsolation())


async def test_distributed_handler_rejects_mismatched_fsm_identity(redis_client):
    bot = Bot("123456:ABC")
    dispatcher = Dispatcher()
    runtime = FakeRuntime(bot)
    runtime.coordinator = RedisCoordinator(redis=redis_client, prefix=f"audit-fsm:{uuid4().hex}")
    called = []

    class ReplaceState(BaseMiddleware):
        async def __call__(self, handler, event, data):
            data["state"] = FSMContext(
                storage=dispatcher.storage,
                key=StorageKey(bot_id=bot.id, chat_id=999, user_id=999),
            )
            return await handler(event, data)

    dispatcher.update.outer_middleware(ReplaceState())
    install(runtime, dispatcher, lifecycle=False)

    @dispatcher.message()
    async def handler(message):
        called.append(True)

    try:
        with pytest.raises(ConfigurationError, match="identities differ"):
            await dispatcher.feed_update(bot, Update(update_id=1, message=message()))
        assert not called
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_cancelled_local_fsm_waiter_leaves_no_scope_or_redis_lease(redis_client):
    coord = RedisCoordinator(redis=redis_client, prefix=f"audit-fsm:{uuid4().hex}")
    isolation = SimpleEventIsolation()
    coord.configure_fsm_isolation(isolation)
    storage_key = StorageKey(bot_id=KEY.bot_id, chat_id=KEY.chat_id, user_id=KEY.user_id)

    async def waiter():
        async with coord.hold(KEY):
            pytest.fail("occupied local FSM lock entered")

    async with isolation.lock(key=storage_key):
        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.01)
        assert coord.active_scopes == 1
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert coord.active_scopes == 0
        assert await redis_client.get(coord.lock_key(KEY)) is None
    await isolation.close()


@pytest.mark.parametrize("change", ["remove", "isolation", "reorder"])
async def test_changed_fsm_configuration_fails_closed_before_borrowing(redis_client, change):
    bot = Bot("123456:ABC")
    isolation = SimpleEventIsolation()
    dispatcher = Dispatcher(events_isolation=isolation)
    runtime = FakeRuntime(bot)
    runtime.coordinator = RedisCoordinator(redis=redis_client, prefix=f"audit-fsm:{uuid4().hex}")
    install(runtime, dispatcher, lifecycle=False)
    if change in {"remove", "reorder"}:
        dispatcher.update.outer_middleware.unregister(dispatcher.fsm)
    if change == "reorder":
        dispatcher.update.outer_middleware(dispatcher.fsm)
    if change == "isolation":
        dispatcher.fsm.events_isolation = SimpleEventIsolation()
    try:
        with pytest.raises(ConfigurationError, match="configuration changed"):
            await asyncio.wait_for(
                dispatcher.feed_update(bot, Update(update_id=1, message=message())), 5
            )
    finally:
        await dispatcher.fsm.close()
        await isolation.close()
        await bot.session.close()


@pytest.mark.parametrize("with_bot_id", [False, True])
async def test_redis_fsm_key_builder_must_preserve_lock_identity(redis_client, with_bot_id):
    from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage

    bot = Bot("123456:ABC")
    storage = RedisStorage(
        redis=redis_client,
        key_builder=DefaultKeyBuilder(prefix=f"audit-fsm:{uuid4().hex}", with_bot_id=with_bot_id),
    )
    dispatcher = Dispatcher(storage=storage)
    runtime = FakeRuntime(bot)
    runtime.coordinator = RedisCoordinator(redis=redis_client, prefix=f"audit-fsm:{uuid4().hex}")
    try:
        if with_bot_id:
            install(runtime, dispatcher, lifecycle=False)
            assert dispatcher.get("_aiogram_idle_installed")
        else:
            with pytest.raises(ConfigurationError, match="with_bot_id=True"):
                install(runtime, dispatcher, lifecycle=False)
            assert not dispatcher.get("_aiogram_idle_installed")
    finally:
        await dispatcher.fsm.events_isolation.close()
        await bot.session.close()


async def test_colliding_custom_redis_fsm_key_builder_is_rejected(redis_client):
    from aiogram.fsm.storage.base import KeyBuilder
    from aiogram.fsm.storage.redis import RedisStorage

    class CollidingKeys(KeyBuilder):
        def build(self, key, part=None):
            return f"fsm:{part}"  # Separate fields, but alias every identity.

    bot = Bot("123456:ABC")
    dispatcher = Dispatcher(storage=RedisStorage(redis=redis_client, key_builder=CollidingKeys()))
    runtime = FakeRuntime(bot)
    runtime.coordinator = RedisCoordinator(redis=redis_client, prefix=f"audit-fsm:{uuid4().hex}")
    try:
        with pytest.raises(ConfigurationError, match="must separate"):
            install(runtime, dispatcher, lifecycle=False)
    finally:
        await dispatcher.fsm.events_isolation.close()
        await bot.session.close()


@pytest.mark.parametrize("external", [False, True])
async def test_renewal_cancellation_consumes_only_its_own_request(redis_client, external):
    from aiogram_idle.compat import bounded

    owner = None

    class FailRenewal:
        async def execute_command(self, *args):
            if args[0] == "EVAL" and "PEXPIRE" in args[1]:
                if external:
                    asyncio.get_running_loop().call_soon(owner.cancel, "external")
                raise ConnectionError("renewal failed")
            return await redis_client.execute_command(*args)

    coord = RedisCoordinator(
        redis=FailRenewal(),
        prefix=f"audit-cancel:{uuid4().hex}",
        lease_seconds=0.3,
        renew_seconds=0.05,
        io_timeout=0.1,
    )

    async def protected():
        nonlocal owner
        owner = asyncio.current_task()
        baseline = getattr(owner, "cancelling", lambda: 0)()
        with pytest.raises(OwnershipLost):
            async with coord.hold(KEY):
                await asyncio.Event().wait()
        assert getattr(owner, "cancelling", lambda: 0)() == baseline
        # Reuse this exact task: a later owned timeout remains correctly classified.
        with pytest.raises(asyncio.TimeoutError):
            async with bounded(0.01):
                await asyncio.Event().wait()
        assert getattr(owner, "cancelling", lambda: 0)() == baseline
        async with coord.hold(KEY):
            assert coord.scope_token(KEY) is not None

    task = asyncio.create_task(protected())
    if external:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
        assert getattr(task, "cancelling", lambda: 1)() == 1
    else:
        await task
        assert not task.cancelled()
    assert coord.active_scopes == 0
