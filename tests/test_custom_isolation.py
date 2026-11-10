"""Application-owned isolation remains authoritative through real dispatcher updates."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.base import BaseEventIsolation
from aiogram.types import Chat, Message, Update, User
from aiogram_coordination import OwnershipLost as SharedOwnershipLost
from aiogram_coordination import TrackedEventIsolation

from aiogram_idle import (
    IdleConfig,
    IdlePolicies,
    IdleRuntime,
    MemoryIdleBackend,
    OwnershipLost,
    PromptPolicy,
)
from aiogram_idle.clock import ManualClock
from tests.runtime_helpers import Adapter, Presenter
from tests.test_external_sessions import KEY


class ApplicationIsolation(BaseEventIsolation):
    async def close(self):
        pass

    @asynccontextmanager
    async def lock(self, key):
        raise AssertionError("The supplied public lease provider owns acquisition")
        yield


class Lease:
    def __init__(self, key):
        self.key = key
        self.valid = True
        self.lost = asyncio.Event()

    def assert_owned(self):
        if not self.valid:
            raise SharedOwnershipLost("Application lock lost")

    async def wait_lost(self):
        await self.lost.wait()


class Provider:
    def __init__(self, isolation):
        self.isolation = isolation
        self.locks = {}
        self.leases = []

    @asynccontextmanager
    async def acquire(self, key):
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            lease = Lease(key)
            self.leases.append(lease)
            try:
                yield lease
            finally:
                lease.valid = False


def update(index):
    return Update(
        update_id=index,
        message=Message(
            message_id=index,
            date=datetime.now(timezone.utc),
            chat=Chat(id=42, type="private"),
            from_user=User(id=42, is_bot=False, first_name="Test"),
            text=str(index),
        ),
    )


class ApplicationCoordinator:
    """Structural public bridge; deliberately not a built-in coordinator subclass."""

    def __init__(self, isolation):
        from aiogram_idle.coordinator import AiogramMemoryCoordinator

        self.delegate = AiogramMemoryCoordinator(isolation)

    @property
    def fsm_isolation(self):
        return self.delegate.fsm_isolation

    @property
    def active_scopes(self):
        return self.delegate.active_scopes

    def configure_fsm_isolation(self, isolation):
        return self.delegate.configure_fsm_isolation(isolation)

    def borrowed_fsm(self, key):
        return self.delegate.borrowed_fsm(key)

    def hold(self, key):
        return self.delegate.hold(key)

    def scope_token(self, key):
        return self.delegate.scope_token(key)

    def scope_active(self, key):
        return self.delegate.scope_active(key)

    def scope_matches(self, key, scope):
        return self.delegate.scope_matches(key, scope)


def setup(*, bridge=False):
    application = ApplicationIsolation()
    provider = Provider(application)
    dispatcher = Dispatcher(events_isolation=TrackedEventIsolation(application, provider=provider))
    clock = ManualClock(1000)
    runtime = IdleRuntime(
        backend=MemoryIdleBackend(clock=clock, config=IdleConfig()),
        policies=IdlePolicies({"prompt": PromptPolicy()}),
        adapters={"form": Adapter()},
        presenter=Presenter(clock),
        namespace="test",
    )
    if bridge:
        runtime.coordinator = ApplicationCoordinator(dispatcher.fsm.events_isolation)
    runtime.install(dispatcher, lifecycle=False)
    router = Router()
    dispatcher.include_router(router)
    return runtime, dispatcher, router, provider


async def test_custom_isolation_serializes_full_handlers_state_and_worker():
    runtime, dispatcher, router, provider = setup()
    entered, release, worker_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []

    @router.message()
    async def handler(message, state):
        current = await state.get_data()
        calls.append(message.message_id)
        if message.message_id == 1:
            entered.set()
            await release.wait()
        await state.update_data(count=current.get("count", 0) + 1)

    async def worker():
        async with runtime.coordinator.hold(KEY):
            worker_entered.set()

    bot = Bot("123456:TEST")
    first = asyncio.create_task(dispatcher.feed_update(bot, update(1)))
    await entered.wait()
    second = asyncio.create_task(dispatcher.feed_update(bot, update(2)))
    work = asyncio.create_task(worker())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert calls == [1] and not worker_entered.is_set()
    release.set()
    try:
        await asyncio.wait_for(asyncio.gather(first, second, work), 3)
        context = dispatcher.fsm.get_context(bot=bot, chat_id=42, user_id=42)
        assert await context.get_data() == {"count": 2}
        assert len(provider.leases) == 3
    finally:
        await bot.session.close()
        await dispatcher.emit_shutdown()


async def test_lost_application_lease_never_authorizes_another_library_write():
    runtime, dispatcher, router, provider = setup()
    entered = asyncio.Event()
    rejected = []

    @router.message()
    async def handler(message, idle_context):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            try:
                await idle_context.open_session(operation_id="after-loss", lifetime_seconds=100)
            except (OwnershipLost, SharedOwnershipLost):
                rejected.append(True)

    bot = Bot("123456:TEST")
    task = asyncio.create_task(dispatcher.feed_update(bot, update(1)))
    await entered.wait()
    lease = provider.leases[-1]
    lease.valid = False
    lease.lost.set()
    try:
        with pytest.raises((OwnershipLost, SharedOwnershipLost)):
            await asyncio.wait_for(task, 3)
        assert rejected == [True]
        assert await runtime.backend.load(KEY) is None
    finally:
        await bot.session.close()
        await dispatcher.emit_shutdown()


async def test_structural_public_coordinator_preserved_and_borrowed():
    runtime, dispatcher, router, _ = setup(bridge=True)
    assert isinstance(runtime.coordinator, ApplicationCoordinator)
    seen = []

    @router.message()
    async def handler(message, idle_context):
        seen.append(runtime.coordinator.scope_active(runtime.coordinator.scope_token(KEY)))

    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    try:
        await dispatcher.feed_update(bot, update(1))
        assert seen == [True]
    finally:
        await bot.session.close()
        await dispatcher.fsm.close()


@pytest.mark.parametrize("custom_type", ["subclass", "builtin"])
@pytest.mark.parametrize(
    "supplied_by", ["constructor", "setter", "backend", "backend_after_constructor"]
)
async def test_custom_coordinator_without_fsm_bridge_is_not_replaced(custom_type, supplied_by):
    from aiogram.fsm.storage.memory import SimpleEventIsolation

    from aiogram_idle import ConfigurationError
    from aiogram_idle.coordinator import MemoryCoordinator

    class CustomCoordinator(MemoryCoordinator):
        pass

    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    custom = CustomCoordinator() if custom_type == "subclass" else MemoryCoordinator()
    backend = MemoryIdleBackend()
    if supplied_by == "backend":
        backend.bind_coordinator(custom)
    runtime = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"prompt": PromptPolicy()}),
        adapters={"form": Adapter()},
        presenter=Presenter(ManualClock(1000)),
        namespace="test",
        isolation=custom if supplied_by == "constructor" else None,
    )
    if supplied_by == "setter":
        runtime.coordinator = custom
    if supplied_by == "backend_after_constructor":
        backend.bind_coordinator(custom)
    with pytest.raises(ConfigurationError, match="BorrowedFsmCoordinator"):
        runtime.install(dispatcher, lifecycle=False)
    assert runtime.coordinator is custom
    await dispatcher.fsm.close()
