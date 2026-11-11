"""Redis review: revoked handler draining and independently stored application FSM."""

import asyncio
from uuid import uuid4

import pytest
from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.types import Update

from aiogram_nav import ConfigurationError, ConversationKey, OwnershipLost
from aiogram_nav.storage.redis import RedisNavigationRepository
from tests.test_examples import incoming
from tests.test_redis_coordinator import coordinator
from tests.test_redis_fsm import harness


async def test_revoked_owner_remains_active_until_handler_finishes(nav_redis_client):
    prefix = f"review:nav:{uuid4().hex}"
    repo = RedisNavigationRepository(redis=nav_redis_client, prefix=prefix)
    coord = coordinator(nav_redis_client, prefix)
    repo.coordinator = coord
    key = ConversationKey("test", 1, 42, 42)
    entered, revoked, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def owner():
        with pytest.raises(OwnershipLost):
            async with coord.hold(key):
                entered.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    revoked.set()
                    # Model an application unwinding slow cleanup after lease loss.
                    await finish.wait()

    task = asyncio.create_task(owner())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await nav_redis_client.set(coord.lock_key(key), "successor", px=5000)
        await asyncio.wait_for(revoked.wait(), 2)
        assert coord.scope_token(key) is None
        assert coord.active_scopes == 1
        with pytest.raises(ConfigurationError):
            await repo.close()
        finish.set()
        await asyncio.wait_for(task, 2)
        assert coord.active_scopes == 0
    finally:
        finish.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("disabled", [False, True])
async def test_real_shared_redis_fsm_and_independent_clients(nav_redis_url, disabled):
    from aiogram.fsm.storage.redis import RedisStorage
    from redis.asyncio import Redis

    prefix = f"review:nav:{uuid4().hex}"
    clients = [Redis.from_url(nav_redis_url) for _ in range(2)]
    storages = [
        RedisStorage(
            redis=client,
            key_builder=DefaultKeyBuilder(prefix=prefix + ":fsm", with_bot_id=True),
        )
        for client in clients
    ]
    runtimes = [
        await harness(client, prefix, disabled=disabled, storage=storage)
        for client, storage in zip(clients, storages, strict=True)
    ]
    entered, release, done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    order = []
    routers = [Router(), Router()]

    @routers[0].message()
    async def first(message, nav_context, state=None):
        entered.set()
        await release.wait()
        if state is not None:
            await state.set_state("ready")
            await state.set_data({"version": 1})
        order.append("first")

    async def second(message, nav_context, state=None):
        if state is not None:
            assert await state.get_data() == {"version": 1}
            await state.update_data(version=2)
        order.append("second")
        done.set()

    routers[1].message.register(second, *([] if disabled else [StateFilter("ready")]))
    for runtime, router in zip(runtimes, routers, strict=True):
        runtime[0].include_router(router)
    tasks = []
    try:
        tasks.append(
            asyncio.create_task(
                runtimes[0][0].feed_update(
                    runtimes[0][2], Update(update_id=1, message=incoming("one"))
                )
            )
        )
        await asyncio.wait_for(entered.wait(), 2)
        tasks.append(
            asyncio.create_task(
                runtimes[1][0].feed_update(
                    runtimes[1][2], Update(update_id=2, message=incoming("two"))
                )
            )
        )
        await asyncio.sleep(0.05)
        assert not done.is_set()
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 3)
        assert order == ["first", "second"]
        if not disabled:
            state = runtimes[0][0].fsm.get_context(bot=runtimes[0][2], chat_id=42, user_id=42)
            assert await state.get_data() == {"version": 2}
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for dispatcher, _, bot in runtimes:
            await dispatcher.fsm.close()
            await bot.session.close()
        for client in clients:
            await client.aclose()


@pytest.mark.parametrize(
    "value", [True, None, "30", float("inf"), float("nan"), 1e308, 10**1000, 1e20]
)
def test_coordinator_rejects_invalid_lease_before_network(value):
    from aiogram_nav.storage.redis_coordinator import RedisCoordinator

    with pytest.raises(ConfigurationError):
        RedisCoordinator(redis=object(), lease_seconds=value)


@pytest.mark.parametrize("prefix", [True, 1, None, "", "a b", "x" * 257])
def test_coordinator_rejects_invalid_prefix_before_network(prefix):
    from aiogram_nav.storage.redis_coordinator import RedisCoordinator

    with pytest.raises(ConfigurationError):
        RedisCoordinator(redis=object(), prefix=prefix)


async def test_custom_simple_isolation_cannot_be_borrowed(nav_redis_client):
    from contextlib import asynccontextmanager

    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import SimpleEventIsolation

    from aiogram_nav import Navigation, NavigationRegistry, Node, ScreenSpec, TextPresenter
    from tests.test_examples import RecordingSession

    class UnsafeIsolation(SimpleEventIsolation):
        @asynccontextmanager
        async def lock(self, key):
            yield

    repo = RedisNavigationRepository(redis=nav_redis_client, prefix=f"review:nav:{uuid4().hex}")
    unsafe = UnsafeIsolation()
    from aiogram_nav import AiogramMemoryCoordinator

    with pytest.raises(ConfigurationError):
        AiogramMemoryCoordinator(unsafe)
    with pytest.raises(ConfigurationError):
        repo.coordinator.configure_fsm_isolation(unsafe)
    dispatcher = Dispatcher(events_isolation=unsafe)
    bot = Bot("123456:ABC", session=RecordingSession())

    async def screen(request):
        return ScreenSpec("main")

    nav = Navigation(
        registry=NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="screen")]),
        repository=repo,
        presenter=TextPresenter({"screen": screen}, bot),
    )
    try:
        with pytest.raises(ConfigurationError):
            nav.install(dispatcher)
        assert not dispatcher.get("_aiogram_nav_installed")
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
