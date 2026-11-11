"""An application provider supplies proof without replacing its FSM storage."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiogram import Dispatcher, F, Router
from aiogram.fsm.storage.base import BaseEventIsolation
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from aiogram_coordination import TrackedEventIsolation

from aiogram_nav import ConversationKey
from tests.test_dispatcher import harness
from tests.test_examples import incoming


class ApplicationIsolation(BaseEventIsolation):
    def __init__(self):
        self.locks = {}
        self.acquisitions = 0
        self.closed = False

    @asynccontextmanager
    async def lock(self, key):
        async with self.locks.setdefault(key, asyncio.Lock()):
            self.acquisitions += 1
            yield

    async def close(self):
        self.closed = True


@dataclass
class Lease:
    key: object
    done: asyncio.Event

    @property
    def valid(self):
        return not self.done.is_set()

    def assert_owned(self):
        assert self.valid

    async def wait_lost(self):
        await self.done.wait()


class Provider:
    def __init__(self, isolation):
        self.isolation = isolation
        self.leases = []

    @asynccontextmanager
    async def acquire(self, key):
        async with self.isolation.lock(key):
            lease = Lease(key, asyncio.Event())
            self.leases.append(lease)
            try:
                yield lease
            finally:
                lease.done.set()


async def test_custom_isolation_serializes_updates_and_direct_actions_without_recursive_lock():
    _, nav, bot, _ = harness()
    application = ApplicationIsolation()
    tracked = TrackedEventIsolation(application, provider=Provider(application))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage, events_isolation=tracked)
    nav.install(dp)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    app = Router()

    @app.message(F.text == "business")
    async def handler(message, state, nav_context):
        assert tracked.owns(state.key)
        assert nav.coordinator.scope_token(nav_context.key) is not None
        calls.append("entered")
        entered.set()
        await release.wait()
        await state.update_data(application_owned=True)
        calls.append("finished")

    dp.include_router(app)
    first = asyncio.create_task(
        dp.feed_update(bot, Update(update_id=1, message=incoming("business")))
    )
    await entered.wait()
    second = asyncio.create_task(
        dp.feed_update(bot, Update(update_id=2, message=incoming("business")))
    )
    action = asyncio.create_task(
        nav.for_conversation(ConversationKey("default", bot.id, 42, 42)).go(
            "main", operation_id="direct-worker"
        )
    )
    try:
        await asyncio.sleep(0.02)
        assert calls == ["entered"] and not second.done() and not action.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second, action), timeout=3)
        assert calls == ["entered", "finished", "entered", "finished"]
        assert application.acquisitions == 3
        assert dp.storage is storage and dp.fsm.events_isolation is tracked
        await dp.fsm.close()
        assert not application.closed
    finally:
        release.set()
        for task in (first, second, action):
            if not task.done():
                task.cancel()
        await asyncio.gather(first, second, action, return_exceptions=True)
        await bot.session.close()


async def test_direct_custom_fsm_loss_keeps_navigation_error_family():
    import pytest

    from aiogram_nav import AiogramMemoryCoordinator, NavigationError, OwnershipLost

    application = ApplicationIsolation()
    provider = Provider(application)
    tracked = TrackedEventIsolation(application, provider=provider)
    coordinator = AiogramMemoryCoordinator(tracked)
    entered = asyncio.Event()

    async def worker():
        async with coordinator.hold(ConversationKey("default", 1, 42, 42)):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(worker())
    await entered.wait()
    provider.leases[0].done.set()
    with pytest.raises(OwnershipLost) as caught:
        await task
    assert isinstance(caught.value, NavigationError)


async def test_structural_fsm_coordinator_bridge_is_not_replaced_by_installer():
    from aiogram_nav import AiogramMemoryCoordinator

    application = ApplicationIsolation()
    tracked = TrackedEventIsolation(application, provider=Provider(application))
    base = AiogramMemoryCoordinator(tracked)

    class ApplicationBridge:
        borrowed_calls = 0

        @property
        def active_scopes(self):
            return base.active_scopes

        @property
        def fsm_isolation(self):
            return base.fsm_isolation

        def configure_fsm_isolation(self, isolation):
            base.configure_fsm_isolation(isolation)

        def hold(self, key):
            return base.hold(key)

        @asynccontextmanager
        async def borrowed_fsm(self, key):
            self.borrowed_calls += 1
            async with base.borrowed_fsm(key):
                yield

        def scope_token(self, key):
            return base.scope_token(key)

        def scope_active(self, token):
            return base.scope_active(token)

        def scope_matches(self, key, token):
            return base.scope_matches(key, token)

    _, nav, bot, _ = harness()
    bridge = ApplicationBridge()
    nav.coordinator = bridge
    dp = Dispatcher(events_isolation=tracked)
    nav.install(dp)
    app = Router()

    @app.message()
    async def handler(message, nav_context):
        await nav_context.go("main")

    dp.include_router(app)
    try:
        await dp.feed_update(bot, Update(update_id=1, message=incoming("show")))
        assert nav.coordinator is bridge
        assert bridge.borrowed_calls == 1
        assert application.acquisitions == 1
    finally:
        await dp.fsm.close()
        await bot.session.close()


async def test_installer_rejects_custom_coordinator_without_borrowing_capability():
    import pytest

    from aiogram_nav import ConfigurationError, MemoryCoordinator

    class ApplicationCoordinator(MemoryCoordinator):
        pass

    _, nav, bot, _ = harness()
    custom = ApplicationCoordinator()
    nav.coordinator = custom
    application = ApplicationIsolation()
    dp = Dispatcher(
        events_isolation=TrackedEventIsolation(application, provider=Provider(application))
    )
    try:
        with pytest.raises(ConfigurationError, match="BorrowedFsmCoordinator"):
            nav.install(dp)
        assert nav.coordinator is custom
    finally:
        await dp.fsm.close()
        await bot.session.close()


async def test_installer_retains_explicit_exact_memory_coordinator_semantics():
    import pytest

    from aiogram_nav import ConfigurationError, MemoryCoordinator, Navigation

    for source in ("constructor", "setter", "repository", "repository_after_constructor"):
        supplied_in_constructor = source == "constructor"
        _, original, bot, _ = harness()
        custom = MemoryCoordinator()
        nav = Navigation(
            registry=original.registry,
            repository=original.repository,
            presenter=original.presenter,
            isolation=custom if supplied_in_constructor else None,
        )
        if source == "setter":
            nav.coordinator = custom
        elif source == "repository_after_constructor":
            nav.repository.bind_coordinator(custom)
        elif source == "repository":
            original.repository.bind_coordinator(custom)
            nav = Navigation(
                registry=original.registry,
                repository=original.repository,
                presenter=original.presenter,
            )
        application = ApplicationIsolation()
        dp = Dispatcher(
            events_isolation=TrackedEventIsolation(application, provider=Provider(application))
        )
        try:
            with pytest.raises(ConfigurationError, match="BorrowedFsmCoordinator"):
                nav.install(dp)
            assert nav.coordinator is custom
        finally:
            await dp.fsm.close()
            await bot.session.close()
