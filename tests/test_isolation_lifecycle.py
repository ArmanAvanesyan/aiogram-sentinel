"""Queued acquisition, release tails and cancellation provenance."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.memory import SimpleEventIsolation

from aiogram_coordination import (
    AiogramMemoryCoordinator,
    ConfigurationError,
    OwnershipLost,
    RedisCoordinator,
    RenewableRedisEventIsolation,
    TrackedEventIsolation,
)
from tests.test_isolation import CONVERSATION, KEY, ApplicationIsolation, Lease, Provider, wrapper


async def test_close_refuses_pending_application_lock_acquisition():
    isolation, app, _ = wrapper()
    queued = asyncio.Event()
    entered = []

    async def waiter():
        queued.set()
        async with isolation.lock(KEY):
            entered.append(True)

    async with app.lock(KEY):
        task = asyncio.create_task(waiter())
        await queued.wait()
        assert isolation.active_scopes == 1
        with pytest.raises(ConfigurationError, match="Drain"):
            await isolation.close()
        assert entered == []
    await task
    assert entered == [True]
    await isolation.close()
    with pytest.raises(ConfigurationError):
        async with isolation.lock(KEY):
            pytest.fail("closed isolation admitted work")


@pytest.mark.parametrize(
    "field,value",
    [("business_connection_id", "a"), ("business_connection_id", "b"), ("destiny", "other")],
)
async def test_private_only_redis_builder_rejects_extra_dimensions(field, value):
    from dataclasses import replace

    provider = RenewableRedisEventIsolation(
        redis=object(), key_builder=DefaultKeyBuilder(with_bot_id=True)
    )
    with pytest.raises(ConfigurationError, match="dimensions"):
        async with provider.acquire(replace(KEY, **{field: value})):
            pytest.fail("lossy identity admitted")


async def test_default_redis_builder_separates_full_fsm_dimensions(redis_client):
    import uuid
    from dataclasses import replace

    provider = RenewableRedisEventIsolation(
        redis=redis_client,
        key_builder=DefaultKeyBuilder(
            prefix="full:" + uuid.uuid4().hex,
            with_bot_id=True,
            with_business_connection_id=True,
            with_destiny=True,
        ),
    )
    assert provider.supported_dimensions == {"thread_id", "business_connection_id", "destiny"}
    first = replace(KEY, business_connection_id="a", destiny="one", thread_id=1)
    second = replace(KEY, business_connection_id="b", destiny="two", thread_id=2)
    async with provider.acquire(first) as a, provider.acquire(second) as b:
        assert a.valid and b.valid and a.key != b.key
        assert provider.coordinator.active_scopes == 2


async def test_custom_builder_cannot_alias_all_nondefault_business_values():
    class PresenceOnlyBuilder(DefaultKeyBuilder):
        def build(self, key, part=None):
            from dataclasses import replace

            base = super().build(replace(key, business_connection_id=None), part)
            return base + (":business" if key.business_connection_id else "")

    provider = RenewableRedisEventIsolation(
        redis=object(), key_builder=PresenceOnlyBuilder(with_bot_id=True)
    )
    assert "business_connection_id" not in provider.supported_dimensions
    from dataclasses import replace

    for value in ("a", "b"):
        with pytest.raises(ConfigurationError):
            async with provider.acquire(replace(KEY, business_connection_id=value)):
                pytest.fail("aliased business identity admitted")


async def test_structural_borrowed_fsm_bridge_without_concrete_coordinator_type():
    from aiogram_coordination import BorrowedFsmCoordinator

    isolation, _, _ = wrapper()
    delegate = AiogramMemoryCoordinator(isolation)

    class ApplicationBridge:
        @property
        def fsm_isolation(self):
            return delegate.fsm_isolation

        def configure_fsm_isolation(self, value):
            delegate.configure_fsm_isolation(value)

        def borrowed_fsm(self, key):
            return delegate.borrowed_fsm(key)

        @property
        def active_scopes(self):
            return delegate.active_scopes

        def hold(self, key):
            return delegate.hold(key)

        def scope_token(self, key):
            return delegate.scope_token(key)

        def scope_active(self, token):
            return delegate.scope_active(token)

        def scope_matches(self, key, token):
            return delegate.scope_matches(key, token)

    bridge = ApplicationBridge()
    assert isinstance(bridge, BorrowedFsmCoordinator)
    assert not isinstance(bridge, AiogramMemoryCoordinator)
    bridge.configure_fsm_isolation(isolation)
    with pytest.raises(ConfigurationError):
        bridge.configure_fsm_isolation(TrackedEventIsolation(SimpleEventIsolation()))
    with pytest.raises(OwnershipLost):
        async with bridge.borrowed_fsm(CONVERSATION):
            pytest.fail("missing FSM scope admitted")
    async with isolation.lock(KEY), bridge.borrowed_fsm(CONVERSATION):
        token = bridge.scope_token(CONVERSATION)
        assert token is not None and bridge.scope_matches(CONVERSATION, token)
        assert bridge.scope_active(token)
        assert bridge.active_scopes == 1
    async with bridge.hold(CONVERSATION):
        assert isolation.owns(KEY)


async def test_close_waits_for_provider_release_tail():
    app = ApplicationIsolation()
    release_entered, release_allowed = asyncio.Event(), asyncio.Event()

    class SlowProvider(Provider):
        @asynccontextmanager
        async def acquire(self, key):
            async with super().acquire(key) as lease:
                try:
                    yield lease
                finally:
                    release_entered.set()
                    await release_allowed.wait()

    isolation = TrackedEventIsolation(app, provider=SlowProvider(app), close_delegate=True)

    async def owner():
        async with isolation.lock(KEY):
            pass

    task = asyncio.create_task(owner())
    await release_entered.wait()
    assert isolation.active_scopes == 1 and not isolation.owns(KEY)
    with pytest.raises(ConfigurationError, match="Drain"):
        await isolation.close()
    assert not app.closed
    release_allowed.set()
    await task
    assert isolation.active_scopes == 0
    await isolation.close()
    assert app.closed


@pytest.mark.parametrize("distributed", [False, True])
async def test_coordinator_drain_includes_outer_fsm_release_tail(redis_client, distributed):
    import uuid

    app = ApplicationIsolation()
    release_entered, release_allowed = asyncio.Event(), asyncio.Event()

    class SlowProvider(Provider):
        @asynccontextmanager
        async def acquire(self, key):
            async with super().acquire(key) as lease:
                try:
                    yield lease
                finally:
                    release_entered.set()
                    await release_allowed.wait()

    isolation = TrackedEventIsolation(app, provider=SlowProvider(app))
    coordinator = (
        RedisCoordinator(redis=redis_client, prefix="outer-tail:" + uuid.uuid4().hex)
        if distributed
        else AiogramMemoryCoordinator(isolation)
    )
    coordinator.configure_fsm_isolation(isolation)

    async def owner():
        async with isolation.lock(KEY), coordinator.borrowed_fsm(CONVERSATION):
            pass

    task = asyncio.create_task(owner())
    await release_entered.wait()
    assert coordinator.active_scopes == 1 and isolation.active_scopes == 1
    assert coordinator.scope_token(CONVERSATION) is None
    release_allowed.set()
    await task
    assert coordinator.active_scopes == isolation.active_scopes == 0


async def test_external_cancel_without_message_wins_simultaneous_revocation():
    isolation, app, provider = wrapper()
    ready = asyncio.Event()

    class RacingLease(Lease):
        async def wait_lost(self):
            await self.lost.wait()
            # Queued before owner wakeup; Python 3.10 can otherwise retain the
            # delivered old marker while a newer cancel(None) is outstanding.
            asyncio.get_running_loop().call_soon(task.cancel)

    @asynccontextmanager
    async def acquire(key):
        async with app.lock(key):
            lease = RacingLease(key, asyncio.Event())
            provider.leases.append(lease)
            yield lease

    provider.acquire = acquire

    async def owner():
        async with isolation.lock(KEY):
            ready.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(owner())
    await ready.wait()
    provider.leases[-1].lost.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert isolation.active_scopes == 0
