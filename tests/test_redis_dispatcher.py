"""Dispatcher FSM handlers retain distributed idle coordination."""

import asyncio
from uuid import uuid4

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import Update

from aiogram_idle.integration import install
from aiogram_idle.storage.redis_coordinator import RedisCoordinator
from tests.test_telegram import KEY, FakeRuntime, message


@pytest.mark.parametrize("fsm_isolated", [False, True])
async def test_distributed_coordinator_protects_full_fsm_handler(redis_client, fsm_isolated):
    prefix = f"test-dispatch:{uuid4().hex}"
    coordinator = RedisCoordinator(redis=redis_client, prefix=prefix)
    worker = RedisCoordinator(redis=redis_client, prefix=prefix)
    bot = Bot("123456:ABC")
    runtime = FakeRuntime(bot)
    runtime.coordinator = coordinator
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation() if fsm_isolated else None)
    install(runtime, dispatcher, lifecycle=False)
    assert runtime.coordinator is coordinator
    entered, release, worker_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()

    @dispatcher.message()
    async def handler(message, state: FSMContext):
        assert coordinator.scope_token(KEY) is not None
        await state.set_state("editing")
        entered.set()
        await release.wait()
        await state.update_data(saved=True)

    async def background():
        async with worker.hold(KEY):
            worker_entered.set()

    update = asyncio.create_task(
        dispatcher.feed_update(bot, Update(update_id=1, message=message()))
    )
    waiter = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        waiter = asyncio.create_task(background())
        await asyncio.sleep(0.05)
        assert not worker_entered.is_set()
        release.set()
        await asyncio.wait_for(update, timeout=5)
        await asyncio.wait_for(waiter, timeout=5)
        context = dispatcher.fsm.get_context(bot=bot, chat_id=42, user_id=42)
        assert await context.get_state() == "editing"
        assert await context.get_data() == {"saved": True}
    finally:
        release.set()
        update.cancel()
        if waiter:
            waiter.cancel()
        await asyncio.gather(update, *([waiter] if waiter else []), return_exceptions=True)
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_separate_dispatchers_reload_redis_fsm_after_distributed_wait(redis_client):
    from aiogram.filters import StateFilter
    from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage

    prefix = f"test-fsm:{uuid4().hex}"
    bot = Bot("123456:ABC")
    storage = RedisStorage(
        redis=redis_client, key_builder=DefaultKeyBuilder(prefix=prefix, with_bot_id=True)
    )
    dispatchers = [Dispatcher(storage=storage), Dispatcher(storage=storage)]
    for dispatcher in dispatchers:
        runtime = FakeRuntime(bot)
        runtime.coordinator = RedisCoordinator(redis=redis_client, prefix=prefix)
        install(runtime, dispatcher, lifecycle=False)
    entered, release = asyncio.Event(), asyncio.Event()
    observed = []

    @dispatchers[0].message()
    async def first(message, state: FSMContext):
        entered.set()
        await release.wait()
        await state.set_state("editing")
        await state.set_data({"draft": "saved"})

    @dispatchers[1].message(StateFilter("editing"))
    async def second(message, state: FSMContext):
        observed.append(await state.get_data())

    one = asyncio.create_task(
        dispatchers[0].feed_update(bot, Update(update_id=1, message=message()))
    )
    two = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        two = asyncio.create_task(
            dispatchers[1].feed_update(bot, Update(update_id=2, message=message()))
        )
        await asyncio.sleep(0.05)
        assert not two.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(one, two), timeout=5)
        assert observed == [{"draft": "saved"}]
    finally:
        release.set()
        one.cancel()
        if two:
            two.cancel()
        await asyncio.gather(one, *([two] if two else []), return_exceptions=True)
        # Caller owns this fixture client, so do not close shared RedisStorage.
        await storage.set_state(dispatchers[0].fsm.get_context(bot=bot, chat_id=42, user_id=42).key)
        await storage.set_data(
            dispatchers[0].fsm.get_context(bot=bot, chat_id=42, user_id=42).key, {}
        )
        await bot.session.close()
