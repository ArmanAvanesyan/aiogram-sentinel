"""Distributed ownership protects real dispatcher handlers and application FSM writes."""

import asyncio
import uuid

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import Update

from aiogram_nav import (
    ConfigurationError,
    Navigation,
    NavigationRegistry,
    Node,
    ScreenSpec,
    TextPresenter,
)
from aiogram_nav.isolation import MemoryCoordinator
from aiogram_nav.storage.redis import RedisNavigationRepository
from tests.test_examples import RecordingSession, incoming


async def harness(client, prefix, *, disabled=False, storage=None):
    bot = Bot("123456:ABC", session=RecordingSession())
    dispatcher = Dispatcher(
        events_isolation=SimpleEventIsolation(), disable_fsm=disabled, storage=storage
    )

    async def screen(request):
        return ScreenSpec(request.node_id)

    repository = RedisNavigationRepository(redis=client, prefix=prefix)
    await repository.initialize()
    nav = Navigation(
        registry=NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="screen")]),
        repository=repository,
        presenter=TextPresenter({"screen": screen}, bot),
    )
    nav.install(dispatcher)
    return dispatcher, nav, bot


@pytest.mark.parametrize("disabled", [False, True])
async def test_separate_runtimes_serialize_entire_handler_and_refresh_fsm(
    nav_redis_client, disabled
):
    prefix = f"test-fsm:{uuid.uuid4().hex}"
    storage = MemoryStorage()
    one = await harness(nav_redis_client, prefix, disabled=disabled, storage=storage)
    two = await harness(nav_redis_client, prefix, disabled=disabled, storage=storage)
    entered, release, second_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    order = []
    first_router, second_router = Router(), Router()

    @first_router.message()
    async def first(message, nav_context, state: FSMContext | None = None):
        assert one[1].coordinator.scope_token(nav_context.key) is not None
        entered.set()
        await release.wait()
        if state is not None:
            await state.set_data({"counter": 1})
            await state.set_state("ready")
        order.append("first")

    async def second(message, nav_context, state: FSMContext | None = None):
        assert two[1].coordinator.scope_token(nav_context.key) is not None
        if state is not None:
            assert await state.get_data() == {"counter": 1}
            await state.update_data(counter=2)
        order.append("second")
        second_entered.set()

    if disabled:
        second_router.message.register(second)
    else:
        # FSM middleware may have read None before waiting on the Redis lock.
        # The navigation middleware must refresh it inside distributed ownership.
        second_router.message.register(second, StateFilter("ready"))
    one[0].include_router(first_router)
    two[0].include_router(second_router)
    tasks = []
    try:
        tasks.append(
            asyncio.create_task(
                one[0].feed_update(one[2], Update(update_id=1, message=incoming("first")))
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=3)
        tasks.append(
            asyncio.create_task(
                two[0].feed_update(two[2], Update(update_id=2, message=incoming("second")))
            )
        )
        await asyncio.sleep(0.05)
        assert not second_entered.is_set()
        assert two[1].coordinator.active_scopes == 1
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
        assert order == ["first", "second"]
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for dispatcher, _, bot in (one, two):
            await dispatcher.fsm.close()
            await bot.session.close()


@pytest.mark.parametrize("mutation", ["coordinator", "missing_state", "changed_state", "isolation"])
async def test_distributed_fsm_rejects_changed_coordination(nav_redis_client, mutation):
    dispatcher, nav, bot = await harness(nav_redis_client, f"test-fsm:{uuid.uuid4().hex}")
    if mutation == "coordinator":
        nav.repository.coordinator = MemoryCoordinator()
    elif mutation == "isolation":
        dispatcher.fsm.events_isolation = SimpleEventIsolation()
    else:
        # Insert immediately before navigation, after the original FSM middleware.
        from aiogram import BaseMiddleware
        from aiogram.fsm.storage.base import StorageKey

        class CorruptContext(BaseMiddleware):
            async def __call__(self, handler, event, data):
                if mutation == "missing_state":
                    data.pop("state", None)
                else:
                    data["state"] = FSMContext(
                        storage=dispatcher.storage,
                        key=StorageKey(bot_id=bot.id, chat_id=99, user_id=99),
                    )
                return await handler(event, data)

        middleware = list(dispatcher.update.outer_middleware)[-1]
        dispatcher.update.outer_middleware.unregister(middleware)
        dispatcher.update.outer_middleware(CorruptContext())
        dispatcher.update.outer_middleware(middleware)
    try:
        with pytest.raises(ConfigurationError):
            await dispatcher.feed_update(bot, Update(update_id=10, message=incoming("test")))
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_application_owned_renewable_redis_fsm_isolation(nav_redis_client):
    from aiogram_coordination import RenewableRedisEventIsolation, TrackedEventIsolation

    application = RenewableRedisEventIsolation(redis=nav_redis_client)
    tracked = TrackedEventIsolation(application, provider=application)
    dispatcher = Dispatcher(events_isolation=tracked)
    bot = Bot("123456:ABC", session=RecordingSession())
    repo = RedisNavigationRepository(
        redis=nav_redis_client, prefix=f"custom-fsm:{uuid.uuid4().hex}"
    )
    await repo.initialize()

    async def screen(request):
        return ScreenSpec(request.node_id)

    nav = Navigation(
        registry=NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="screen")]),
        repository=repo,
        presenter=TextPresenter({"screen": screen}, bot),
    )
    nav.install(dispatcher)
    router = Router()
    entered, release = asyncio.Event(), asyncio.Event()
    observed = []

    @router.message()
    async def handler(message, state, nav_context):
        assert tracked.owns(state.key)
        observed.append(message.text)
        if message.text == "first":
            entered.set()
            await release.wait()
        await state.update_data(last=message.text)
        await nav_context.go("main", operation_id=message.text)

    dispatcher.include_router(router)
    tasks = [
        asyncio.create_task(
            dispatcher.feed_update(bot, Update(update_id=1, message=incoming("first")))
        )
    ]
    try:
        await entered.wait()
        tasks.append(
            asyncio.create_task(
                dispatcher.feed_update(bot, Update(update_id=2, message=incoming("second")))
            )
        )
        await asyncio.sleep(0)
        assert observed == ["first"]
        release.set()
        await asyncio.gather(*tasks)
        assert observed == ["first", "second"]
        assert nav.coordinator.fsm_isolation is tracked
        assert await nav_redis_client.ping()
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await dispatcher.fsm.close()
        await bot.session.close()
