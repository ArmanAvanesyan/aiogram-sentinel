"""Optional install admission must not downgrade locks or mutate rejected setup."""

from contextlib import asynccontextmanager

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation

pytest.importorskip("aiogram_nav")
from aiogram_nav import CommandEntry, InputBindings, Navigation, NavigationRegistry, Node

from aiogram_idle.clock import ManualClock
from aiogram_idle.coordinator import MemoryCoordinator
from aiogram_idle.errors import ConfigurationError
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
from aiogram_idle.policies import ExemptPolicy, IdlePolicies
from aiogram_idle.runtime import IdleRuntime
from aiogram_idle.storage.memory import MemoryIdleBackend
from tests.runtime_helpers import Adapter, Presenter
from tests.test_nav_runtime import Screens


def unbound(*, coordinator=None, bindings=None):
    backend = MemoryIdleBackend(clock=ManualClock())
    if coordinator is not None:
        backend.bind_coordinator(coordinator)
    idle = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"none": ExemptPolicy()}),
        adapters={"application": Adapter()},
        presenter=Presenter(backend.clock),
    )
    registry = NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="screen")])
    integration = NavigationIntegration(
        idle=idle, registry=registry, policies=NodePolicies(default="none")
    )
    screens = Screens()
    nav = Navigation(
        registry=registry,
        repository=integration.navigation_repository,
        presenter=screens,
        bindings=bindings,
    )
    return integration, nav, screens


@pytest.mark.parametrize("fsm", [False, True])
async def test_unknown_coordinator_cannot_downgrade_full_handler_isolation(fsm):
    class UnsafeCoordinator(MemoryCoordinator):
        @asynccontextmanager
        async def hold(self, key):
            yield

    integration, nav, original = unbound(coordinator=UnsafeCoordinator())
    dp = Dispatcher(events_isolation=SimpleEventIsolation() if fsm else None)
    stack = list(dp.update.outer_middleware)
    try:
        with pytest.raises(ConfigurationError, match="coordinator"):
            integration.install(dp, navigation=nav)
        assert integration.navigation is None and nav.presenter is original
        assert list(dp.update.outer_middleware) == stack
        assert not dp.get("_aiogram_idle_installed")
        assert not dp.get("_aiogram_nav_installed")
    finally:
        await dp.fsm.close()


async def test_rejected_root_binding_install_preserves_unbound_navigation():
    integration, nav, original = unbound(
        bindings=InputBindings([CommandEntry("main", command="menu", target="main")])
    )
    dp = Dispatcher(events_isolation=SimpleEventIsolation())

    @dp.message()
    async def root(message):
        pass

    coordinator = integration.idle.coordinator
    try:
        with pytest.raises(ConfigurationError, match="Routers"):
            integration.install(dp, navigation=nav)
        assert integration.navigation is None
        assert integration.navigation_repository.navigation is None
        assert nav.presenter is original
        assert integration.idle.coordinator is coordinator
    finally:
        await dp.fsm.close()


async def test_worker_start_prevents_late_dispatcher_install_even_when_idle():
    integration, nav, original = unbound()
    integration.bind(nav)
    await integration.idle.start()
    dp = Dispatcher()
    stack = list(dp.update.outer_middleware)
    try:
        with pytest.raises(ConfigurationError, match="before starting"):
            integration.install(dp, navigation=nav)
        assert not integration._installed
        assert list(dp.update.outer_middleware) == stack
    finally:
        await integration.idle.stop()
        await dp.fsm.close()


async def test_worker_start_prevents_first_headless_navigation_binding():
    integration, nav, original = unbound()
    await integration.idle.start()
    try:
        with pytest.raises(ConfigurationError, match="before starting"):
            integration.bind(nav)
        assert integration.navigation is None and nav.presenter is original
        assert integration.navigation_repository.navigation is None
    finally:
        await integration.idle.stop()


async def test_active_scope_prevents_install_without_mutating_presenter():
    integration, nav, original = unbound()
    dp = Dispatcher()
    from aiogram_idle.models import IdleConversationKey

    key = IdleConversationKey("default", 1, 42, 42)
    try:
        async with integration.idle.coordinator.hold(key):
            with pytest.raises(ConfigurationError, match="before starting"):
                integration.install(dp, navigation=nav)
        assert integration.navigation is None and nav.presenter is original
    finally:
        await dp.fsm.close()


async def test_headless_control_rejects_replaced_reserved_adapter_before_reservation():
    from aiogram_idle.controls import ControlContext
    from aiogram_idle.models import Phase
    from tests.test_nav_runtime import make

    integration, nav, _, clock, key = make()
    await nav.for_conversation(key).go("form", operation_id="entry")
    clock.advance(10)
    await integration.idle.run_once()
    mapped = integration.navigation_repository.mapping.to_idle(key)
    before = await integration.idle.inspect(mapped)
    assert before.idle.phase == Phase.PROMPTED
    integration.idle.adapters["aiogram_nav"] = Adapter()
    with pytest.raises(ConfigurationError, match="writer hooks"):
        await integration.idle.continue_current(ControlContext(mapped, 42, operation_id="answer"))
    assert await integration.idle.inspect(mapped) == before


async def test_queued_handler_revalidates_owner_hooks_after_waiting_for_lock():
    import asyncio

    from aiogram import Bot, Router
    from aiogram.types import Update

    from tests.test_nav_runtime import make
    from tests.test_telegram import message
    from tests.test_telegram_failures import RecordingSession

    bot = Bot("123456:ABC", session=RecordingSession())
    integration, nav, _, _, key = make(bot=bot)
    dispatcher = Dispatcher()
    integration.install(dispatcher, navigation=nav, lifecycle=False)
    business = Router()
    calls = []

    @business.message()
    async def handler(message):
        calls.append("business")

    dispatcher.include_router(business)
    coordinator = integration.idle.coordinator
    mapped = integration.navigation_repository.mapping.to_idle(key)
    update = None
    try:
        async with coordinator.hold(mapped):
            update = asyncio.create_task(
                dispatcher.feed_update(bot, Update(update_id=1, message=message("ordinary")))
            )
            for _ in range(100):
                if coordinator.active_scopes == 2:
                    break
                await asyncio.sleep(0)
            assert coordinator.active_scopes == 2
            integration.idle.adapters["aiogram_nav"] = Adapter()
        with pytest.raises(ConfigurationError, match="writer hooks"):
            await asyncio.wait_for(update, 3)
        assert not calls
    finally:
        if update is not None:
            update.cancel()
            await asyncio.gather(update, return_exceptions=True)
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_headless_initialization_rejects_an_unverified_coordinator():
    class UnsafeCoordinator(MemoryCoordinator):
        @asynccontextmanager
        async def hold(self, key):
            async with self._scope(key):
                yield

    integration, _, _ = unbound(coordinator=UnsafeCoordinator())
    with pytest.raises(ConfigurationError, match="coordinator"):
        await integration.idle.initialize()
    assert await integration.idle.backend.get_config() is None


async def test_headless_initialization_rejects_changed_coordinator_mapping():
    from aiogram_idle.integrations.nav.mapping import IdentityMapping

    integration, nav, _ = unbound()
    integration.bind(nav)
    integration.navigation_repository.coordinator.mapping = IdentityMapping()
    with pytest.raises(ConfigurationError, match="coordination"):
        await integration.idle.initialize()
    assert await integration.idle.backend.get_config() is None


async def test_rejected_late_install_restores_presenter_and_writer(monkeypatch):
    integration, nav, original = unbound()
    dp = Dispatcher()

    def reject(*args, **kwargs):
        raise ConfigurationError("coordinator already bound")

    monkeypatch.setattr("aiogram_idle.integrations.nav.installation.install", reject)
    try:
        with pytest.raises(ConfigurationError, match="already bound"):
            integration.install(dp, navigation=nav)
        assert nav.presenter is original
        assert integration.navigation is None
        assert integration.navigation_repository.navigation is None
        assert nav.bot is None and integration.idle.bot is None
    finally:
        await dp.fsm.close()
