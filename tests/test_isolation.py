"""Verifiable custom isolation, real Dispatcher use and lease-loss handling."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseEventIsolation, DefaultKeyBuilder, StorageKey
from aiogram.fsm.storage.memory import DisabledEventIsolation, SimpleEventIsolation
from aiogram.types import Chat, Message, Update, User

from aiogram_coordination import (
    AiogramMemoryCoordinator,
    ConfigurationError,
    CoordinationKey,
    OwnershipLost,
    RedisCoordinator,
    RenewableRedisEventIsolation,
    TrackedEventIsolation,
)

KEY = StorageKey(bot_id=123456, chat_id=42, user_id=42)
CONVERSATION = CoordinationKey("test", 123456, 42, 42)


@dataclass
class Lease:
    key: StorageKey
    lost: asyncio.Event
    invalid: bool = False

    @property
    def valid(self):
        return not self.invalid and not self.lost.is_set()

    def assert_owned(self):
        if not self.valid:
            raise OwnershipLost("Application scope revoked")

    async def wait_lost(self):
        await self.lost.wait()


class ApplicationIsolation(BaseEventIsolation):
    def __init__(self):
        self.delegate = SimpleEventIsolation()
        self.entries = 0
        self.closed = False

    @asynccontextmanager
    async def lock(self, key):
        async with self.delegate.lock(key=key):
            self.entries += 1
            yield

    async def close(self):
        self.closed = True
        await self.delegate.close()


class Provider:
    def __init__(self, isolation):
        self.isolation = isolation
        self.leases = []
        self.wrong = False

    @asynccontextmanager
    async def acquire(self, key):
        async with self.isolation.lock(key=key):
            lease = Lease(KEY if self.wrong else key, asyncio.Event())
            self.leases.append(lease)
            try:
                yield lease
            finally:
                lease.lost.set()


def wrapper():
    app = ApplicationIsolation()
    provider = Provider(app)
    return TrackedEventIsolation(app, provider=provider), app, provider


async def test_simple_nested_borrow_and_task_scoped_ownership():
    isolation = TrackedEventIsolation(SimpleEventIsolation())
    async with isolation.lock(KEY):
        assert isolation.owns(KEY)
        async with isolation.borrowed(KEY), isolation.lock(KEY):
            assert isolation.active_scopes == 1

        async def child():
            assert not isolation.owns(KEY)
            with pytest.raises(OwnershipLost):
                async with isolation.borrowed(KEY):
                    pass

        await asyncio.create_task(child())
        with pytest.raises(ConfigurationError):
            await isolation.close()
    assert not isolation.owns(KEY)
    await isolation.close()
    with pytest.raises(ConfigurationError):
        async with isolation.lock(KEY):
            pass


async def test_explicit_provider_preserves_application_lock_and_close_ownership():
    isolation, app, provider = wrapper()
    coordinator = AiogramMemoryCoordinator(isolation)
    with pytest.raises(OwnershipLost):
        async with coordinator.borrowed(CONVERSATION):
            pass
    async with isolation.lock(KEY):
        async with coordinator.borrowed(CONVERSATION):
            assert coordinator.owns(CONVERSATION)
        assert app.entries == 1 and provider.leases[0].valid
    await isolation.close()
    assert not app.closed
    app2 = ApplicationIsolation()
    explicit = TrackedEventIsolation(app2, provider=Provider(app2), close_delegate=True)
    await explicit.close()
    assert app2.closed


async def test_custom_provider_loss_revokes_and_cancels_owner():
    isolation, _, provider = wrapper()
    entered = asyncio.Event()

    async def owner():
        async with isolation.lock(KEY):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # Suppression never turns a lost lease into a successful result.
                pass

    task = asyncio.create_task(owner())
    await entered.wait()
    provider.leases[0].lost.set()
    with pytest.raises(OwnershipLost):
        await task
    assert isolation.active_scopes == 0


async def test_external_cancellation_is_not_relabelled_when_lease_also_lost():
    isolation, _, provider = wrapper()
    entered = asyncio.Event()

    async def owner():
        async with isolation.lock(KEY):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(owner())
    await entered.wait()
    provider.leases[0].lost.set()
    task.cancel("external")
    with pytest.raises(asyncio.CancelledError):
        await task
    assert isolation.active_scopes == 0


async def test_borrowed_scope_does_not_mask_application_exception_or_cancellation():
    isolation, _, provider = wrapper()
    async with isolation.lock(KEY):
        with pytest.raises(ValueError, match="application"):
            async with isolation.borrowed(KEY):
                raise ValueError("application")
    # Force invalidation synchronously after entering a borrowed block; no watch
    # scheduling is needed to prove that its exit refuses lost ownership.
    with pytest.raises(OwnershipLost):
        async with isolation.lock(KEY), isolation.borrowed(KEY):
            provider.leases[-1].lost.set()


@pytest.mark.parametrize("value", [None, object(), DisabledEventIsolation()])
def test_opaque_isolation_is_rejected(value):
    with pytest.raises(ConfigurationError):
        TrackedEventIsolation(value)


def test_provider_must_reference_exact_isolation():
    one, two = ApplicationIsolation(), ApplicationIsolation()
    with pytest.raises(ConfigurationError):
        TrackedEventIsolation(one, provider=Provider(two))
    with pytest.raises(ConfigurationError):
        TrackedEventIsolation(SimpleEventIsolation(), close_delegate=1)
    with pytest.raises(ConfigurationError):
        AiogramMemoryCoordinator(object())


async def test_invalid_provider_lease_key_is_rejected():
    isolation, _, provider = wrapper()
    provider.wrong = True
    with pytest.raises(ConfigurationError):
        async with isolation.lock(StorageKey(bot_id=1, chat_id=2, user_id=2)):
            pass


async def test_two_real_dispatcher_updates_and_worker_share_custom_isolation():
    isolation, app, _ = wrapper()
    dp = Dispatcher(events_isolation=isolation)
    coordinator = AiogramMemoryCoordinator(isolation)
    entered, release = asyncio.Event(), asyncio.Event()
    visits = []

    @dp.message()
    async def handler(message: Message, state: FSMContext):
        async with coordinator.borrowed(CONVERSATION):
            current = (await state.get_data()).get("count", 0)
            visits.append(message.message_id)
            if message.message_id == 1:
                entered.set()
                await release.wait()
            await state.update_data(count=current + 1)

    bot = Bot("123456:TEST")

    def update(number):
        return Update(
            update_id=number,
            message=Message(
                message_id=number,
                date=datetime.now(timezone.utc),
                chat=Chat(id=42, type="private"),
                from_user=User(id=42, is_bot=False, first_name="Test"),
                text="x",
            ),
        )

    first = asyncio.create_task(dp.feed_update(bot, update(1)))
    await entered.wait()
    second = asyncio.create_task(dp.feed_update(bot, update(2)))

    async def worker():
        async with coordinator.hold(CONVERSATION):
            visits.append("worker")

    third = asyncio.create_task(worker())
    release.set()
    try:
        await asyncio.gather(first, second, third)
        assert visits[0] == 1 and set(visits[1:]) == {2, "worker"}
        assert (await dp.storage.get_data(KEY))["count"] == 2
        assert app.entries == 3
    finally:
        await bot.session.close()
        await dp.storage.close()
        await isolation.close()


async def test_redis_reference_isolation_renews_and_preserves_client(redis_client):
    import uuid

    provider = RenewableRedisEventIsolation(
        redis=redis_client,
        key_builder=DefaultKeyBuilder(prefix="fsm:" + uuid.uuid4().hex, with_bot_id=True),
        lease_seconds=0.4,
        renew_seconds=0.05,
        io_timeout=0.1,
    )
    isolation = TrackedEventIsolation(provider)
    async with isolation.lock(KEY):
        await asyncio.sleep(0.5)
        assert isolation.owns(KEY)
    await isolation.close()
    await provider.close()
    assert await redis_client.ping()


async def test_redis_coordinator_borrows_verified_custom_fsm(redis_client):
    import uuid

    isolation, app, _ = wrapper()
    coord = RedisCoordinator(redis=redis_client, prefix="both:" + uuid.uuid4().hex)
    coord.configure_fsm_isolation(isolation)
    coord.configure_fsm_isolation(isolation)
    with pytest.raises(OwnershipLost):
        async with coord.borrowed_fsm(CONVERSATION):
            pass
    async with isolation.lock(KEY), coord.borrowed_fsm(CONVERSATION):
        assert coord.fencing(CONVERSATION)
        with pytest.raises(ConfigurationError):
            coord.configure_fsm_isolation(TrackedEventIsolation(SimpleEventIsolation()))
    async with coord.hold(CONVERSATION):
        assert isolation.owns(KEY)
    assert app.entries == 2


def test_redis_reference_requires_lossless_keybuilder():
    with pytest.raises(ConfigurationError):
        RenewableRedisEventIsolation(redis=object(), key_builder=DefaultKeyBuilder())
    with pytest.raises(ConfigurationError):
        RenewableRedisEventIsolation(redis=object(), key_builder=object())


@pytest.mark.parametrize("distributed", [False, True])
async def test_revoked_fsm_lease_immediately_revokes_effect_capability(redis_client, distributed):
    import uuid

    isolation, _, provider = wrapper()
    coordinator = (
        RedisCoordinator(redis=redis_client, prefix="fsm-proof:" + uuid.uuid4().hex)
        if distributed
        else AiogramMemoryCoordinator(isolation)
    )
    if distributed:
        coordinator.configure_fsm_isolation(isolation)
    observed = []
    with pytest.raises(OwnershipLost):
        async with coordinator.hold(CONVERSATION):
            scope = coordinator.scope_token(CONVERSATION)
            assert scope is not None
            provider.leases[-1].invalid = True
            # Even before cancellation can be delivered, no new stage may run.
            assert not coordinator.scope_active(scope)
            assert not coordinator.scope_matches(CONVERSATION, scope)
            assert coordinator.scope_token(CONVERSATION) is None
            assert coordinator.active_scopes >= 1  # still drain the owning task

            async def delegated():
                assert not coordinator.scope_matches(CONVERSATION, scope)

            await asyncio.create_task(delegated())
            with pytest.raises(OwnershipLost):
                async with coordinator.hold(CONVERSATION):
                    observed.append("reacquired")
    assert observed == [] and coordinator.active_scopes == 0
