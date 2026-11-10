"""Optional integration lifecycle and single-middleware coordination regressions."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import Update

pytest.importorskip("aiogram_nav")
from aiogram_nav import (
    CleanupResult,
    CommandEntry,
    ConversationKey,
    InputBindings,
    MessageRef,
    Navigation,
    NavigationRegistry,
    Node,
    RenderResult,
)

from aiogram_idle.clock import ManualClock
from aiogram_idle.config import IdleConfig
from aiogram_idle.controls import ControlContext
from aiogram_idle.errors import ConfigurationError
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
from aiogram_idle.models import Phase
from aiogram_idle.policies import ExemptPolicy, IdlePolicies, PromptPolicy, QuietRestorePolicy
from aiogram_idle.runtime import IdleRuntime
from aiogram_idle.storage.memory import MemoryIdleBackend
from tests.runtime_helpers import Adapter, Presenter
from tests.test_telegram import message as incoming
from tests.test_telegram_failures import RecordingSession


class Screens:
    replay_safe = True

    def __init__(self):
        self.renders = []
        self.cleanups = []

    async def render(self, request):
        self.renders.append(request.node.id)
        return RenderResult(request.view_id, (MessageRef(request.key.chat_id, len(self.renders)),))

    async def cleanup(self, request):
        if request.ensure_owned is not None:
            request.ensure_owned()
        if request.previous is not None:
            self.cleanups.append(request)
        return CleanupResult()


def make(*, bot=None, backend=None, policy=None, session_authority=None):
    clock = backend.clock if backend is not None else ManualClock(1000)
    config = backend.config if backend is not None else IdleConfig(enabled=True)
    backend = backend or MemoryIdleBackend(clock=clock, config=config)
    idle = IdleRuntime(
        backend=backend,
        config=config,
        policies=IdlePolicies(
            {
                "none": ExemptPolicy(),
                "draft": policy or PromptPolicy(after_seconds=10, grace_seconds=10),
            }
        ),
        adapters={"standalone": Adapter()},
        presenter=Presenter(clock),
        namespace="test",
        bot=bot,
        session_authority=session_authority,
    )
    registry = NavigationRegistry(
        roots={"main"},
        nodes=[Node("main", renderer="text"), Node("form", parent="main", renderer="text")],
    )
    integration = NavigationIntegration(
        idle=idle,
        registry=registry,
        policies=NodePolicies(default="none", overrides={"form": "draft"}),
    )
    screens = Screens()
    nav = Navigation(
        registry=registry,
        repository=integration.navigation_repository,
        presenter=screens,
        namespace="test",
        bot=bot,
    )
    integration.bind(nav)
    key = ConversationKey("test", bot.id if bot else 1, 42, 42)
    return integration, nav, screens, clock, key


@pytest.mark.parametrize("answer", ["continue", "cancel"])
async def test_idle_resume_and_restore_commit_screen_and_activity_together(answer):
    integration, nav, screens, clock, key = make()
    await nav.for_conversation(key).go("form", params={"draft_id": "draft"}, operation_id="enter")
    idle_key = integration.navigation_repository.mapping.to_idle(key)
    before = await integration.idle.inspect(idle_key)
    clock.advance(10)
    assert (await integration.idle.run_once()).completed == 1
    assert (await integration.idle.inspect(idle_key)).idle.phase is Phase.PROMPTED
    prompt = await integration.idle.current_prompt(idle_key)
    function = (
        integration.idle.continue_current
        if answer == "continue"
        else integration.idle.cancel_current
    )
    result = await function(
        ControlContext(idle_key, 42, prompt_id=prompt.prompt_id, operation_id="answer")
    )
    assert result.accepted
    after = await integration.idle.inspect(idle_key)
    current = await nav.for_conversation(key).current()
    assert after.idle.operation is None
    assert current.node_id == ("form" if answer == "continue" else "main")
    assert after.activity.activity_revision == current.activity_revision
    assert after.session.session_id == current.session_id == before.session.session_id
    assert screens.renders == ["form", "form" if answer == "continue" else "main"]


@pytest.mark.parametrize("fsm", [False, True])
async def test_combined_middleware_holds_entire_handler_and_injects_both_contexts(fsm):
    bot = Bot("123456:ABC", session=RecordingSession())
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation() if fsm else None)
    integration, nav, _, _, key = make(bot=bot)
    integration.install(dispatcher, navigation=nav, lifecycle=False)
    entered, release = asyncio.Event(), asyncio.Event()
    app = Router()

    @app.message()
    async def handle(message, nav_context, idle_context, navigation_integration):
        assert nav_context.key == key
        assert idle_context.key == integration.navigation_repository.mapping.to_idle(key)
        assert navigation_integration is integration
        entered.set()
        await release.wait()

    dispatcher.include_router(app)
    task = asyncio.create_task(
        dispatcher.feed_update(bot, Update(update_id=1, message=incoming("ordinary")))
    )
    action = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        action = asyncio.create_task(nav.for_conversation(key).go("main", operation_id="other"))
        await asyncio.sleep(0)
        assert not action.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(task, action), 3)
    finally:
        release.set()
        task.cancel()
        if action:
            action.cancel()
        await asyncio.gather(task, *([action] if action else []), return_exceptions=True)
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_idle_prompt_commands_precede_navigation_binding_and_duplicate_install_rejected():
    bot = Bot("123456:ABC", session=RecordingSession())
    dispatcher = Dispatcher()
    integration, nav, _, clock, key = make(bot=bot)
    nav.bind(InputBindings([CommandEntry("cancel", command="cancel", target="form")]))
    integration.install(dispatcher, navigation=nav, lifecycle=False)
    try:
        with pytest.raises(ConfigurationError):
            integration.install(dispatcher, navigation=nav, lifecycle=False)
        await nav.for_conversation(key).go(
            "form", params={"draft_id": "draft"}, operation_id="entry"
        )
        clock.advance(10)
        await integration.idle.run_once()
        await dispatcher.feed_update(bot, Update(update_id=2, message=incoming("/cancel")))
        assert (await nav.for_conversation(key).current()).node_id == "main"
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_real_redis_shared_fsm_state_and_navigation_use_one_lock_domain(
    redis_client, redis_url
):
    from uuid import uuid4

    from aiogram.filters import StateFilter
    from aiogram.fsm.storage.base import DefaultKeyBuilder
    from aiogram.fsm.storage.redis import RedisStorage
    from redis.asyncio import Redis

    from aiogram_idle.storage.redis import RedisIdleBackend

    prefix = f"combined-runtime:{uuid4().hex}"
    second_client = Redis.from_url(redis_url)
    clients = [redis_client, second_client]
    runtimes = []
    routers = [Router(), Router()]
    for client in clients:
        backend = RedisIdleBackend(redis=client, prefix=prefix, config=IdleConfig(enabled=True))
        await backend.initialize()
        bot = Bot("123456:ABC", session=RecordingSession())
        storage = RedisStorage(
            redis=client, key_builder=DefaultKeyBuilder(prefix=prefix + ":fsm", with_bot_id=True)
        )
        dispatcher = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())
        integration, nav, _, _, key = make(bot=bot, backend=backend)
        integration.install(dispatcher, navigation=nav, lifecycle=False)
        runtimes.append((dispatcher, integration, nav, bot, key))
    entered, release, done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    order = []

    @routers[0].message()
    async def first(message, state, nav_context):
        entered.set()
        await release.wait()
        await state.set_data({"counter": 1})
        await state.set_state("ready")
        await nav_context.go("form")
        order.append(1)

    async def second(message, state, nav_context):
        assert await state.get_data() == {"counter": 1}
        await state.update_data(counter=2)
        await nav_context.go("main")
        order.append(2)
        done.set()

    routers[1].message.register(second, StateFilter("ready"))
    for runtime, router in zip(runtimes, routers, strict=True):
        runtime[0].include_router(router)
    tasks = []
    try:
        tasks.append(
            asyncio.create_task(
                runtimes[0][0].feed_update(
                    runtimes[0][3], Update(update_id=1, message=incoming("first"))
                )
            )
        )
        await asyncio.wait_for(entered.wait(), 3)
        tasks.append(
            asyncio.create_task(
                runtimes[1][0].feed_update(
                    runtimes[1][3], Update(update_id=2, message=incoming("second"))
                )
            )
        )
        await asyncio.sleep(0.05)
        assert not done.is_set()
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 5)
        assert order == [1, 2]
        for dispatcher, integration, nav, bot, key in runtimes:
            activity = (
                await integration.idle.inspect(
                    integration.navigation_repository.mapping.to_idle(key)
                )
            ).activity
            current = await nav.for_conversation(key).current()
            assert (
                current.node_id == "main"
                and current.activity_revision == activity.activity_revision == 2
            )
            assert await dispatcher.fsm.get_context(bot=bot, chat_id=42, user_id=42).get_data() == {
                "counter": 2
            }
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for dispatcher, integration, _, bot, _ in runtimes:
            await dispatcher.fsm.close()
            await integration.idle.backend.close()
            await bot.session.close()
        await second_client.aclose()


async def test_quiet_restore_cleans_only_tracked_previous_view_after_atomic_commit():
    integration, nav, screens, clock, key = make(policy=QuietRestorePolicy(after_seconds=10))
    before = await nav.for_conversation(key).go("form", operation_id="entry")
    clock.advance(10)
    assert (await integration.idle.run_once()).completed == 1
    current = await nav.for_conversation(key).current()
    record = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    assert current.node_id == "main" and record.idle.phase is Phase.DISARMED
    assert record.idle.operation is None
    assert screens.cleanups[-1].previous.view_id == before.view_id
    assert screens.cleanups[-1].current.view_id == current.view.view_id
    assert not integration.idle.presenter.questions


@asynccontextmanager
async def reserved_bridge(*, uncertain=False):
    from dataclasses import replace

    from aiogram_nav import RenderRequest

    from aiogram_idle.effects import OperationEffects
    from aiogram_idle.integrations.nav.effects import NavigationEffects
    from aiogram_idle.models import IdleSnapshot, PendingOperation

    integration, nav, _, _, key = make()
    await nav.for_conversation(key).go("form", operation_id="entry")
    idle_key = integration.navigation_repository.mapping.to_idle(key)
    async with integration.idle.coordinator.hold(idle_key):
        record = await integration.idle.inspect(idle_key)
        operation = PendingOperation(
            "owned",
            "continue",
            started_at=integration.idle.clock.now(),
            effects={"nav:effect:literal:send": "started"} if uncertain else {},
        )
        await integration.idle.backend.transition(
            idle_key,
            expected_version=record.store_version,
            operation_id="reserve",
            fingerprint="reserve",
            transform=lambda old: replace(
                old, idle=IdleSnapshot(phase=Phase.RESUMING, operation=operation)
            ),
        )
        current = await nav.for_conversation(key).current()
        request = RenderRequest(
            key,
            "owned",
            nav.registry.get("form"),
            current.params,
            "staged",
            current.session_id,
            current=current,
            expires_at=current.expires_at,
        )
        effects = OperationEffects(integration.idle, idle_key, "owned", None)
        yield integration, nav, NavigationEffects(effects, nav, request), idle_key


@pytest.mark.parametrize("uncertain", [False, True])
async def test_denied_bridge_stage_marks_only_fresh_intent_definitely_unsent(uncertain):
    from aiogram_nav import AccessDenied

    from aiogram_idle.errors import EffectUnknown

    async with reserved_bridge(uncertain=uncertain) as (integration, nav, bridge, key):

        async def deny(*args):
            return False

        nav.authorize = deny
        calls = []

        async def send():
            calls.append("sent")
            return {"message_id": 9}

        with pytest.raises(AccessDenied):
            await bridge.run("send", send, replay_safe=uncertain)
        record = await integration.idle.inspect(key)
        assert record.idle.operation.effects["nav:effect:literal:send"] == (
            "started" if uncertain else "not_sent"
        )
        assert calls == []
        nav.authorize = None
        if uncertain:
            with pytest.raises(EffectUnknown):
                await bridge.run("send", send)
        else:
            assert await bridge.run("send", send) == {"message_id": 9}
            assert calls == ["sent"]


async def test_bridge_rechecks_ownership_after_slow_authorizer_before_sending():
    from aiogram_idle.errors import OwnershipLost

    async with reserved_bridge() as (integration, nav, bridge, key):

        async def revoked(*args):
            integration.idle.coordinator._live_scopes.clear()
            return True

        nav.authorize = revoked
        calls = []

        async def send():
            calls.append("sent")
            return {}

        with pytest.raises(OwnershipLost):
            await bridge.run("send", send)
        assert calls == []


async def test_presenter_stage_named_render_does_not_collide_with_owning_idle_aggregate():
    async with reserved_bridge() as (_, _, bridge, _):

        async def send():
            return {"message_id": 8}

        assert await bridge.effects.run(
            "nav:render", lambda: bridge.run("render", send), replay_safe=True
        ) == {"message_id": 8}
        assert await bridge.run("x" * 128, send) == {"message_id": 8}


async def test_unknown_business_abandon_is_not_replayed_by_safe_navigation_wrapper():
    from dataclasses import replace

    from aiogram_idle.errors import EffectUnknown

    integration, nav, _, clock, key = make()

    class Business:
        calls = 0

        async def abandon(self, context, *, reason, operation_id):
            self.calls += 1
            raise EffectUnknown("business response was lost")

        async def inspect(self, context):
            from aiogram_idle.models import FlowEligibility

            return FlowEligibility()

    business = Business()
    integration.adapters["form"] = business
    await nav.for_conversation(key).go("form", operation_id="entry")
    mapped = integration.navigation_repository.mapping.to_idle(key)
    clock.advance(10)
    await integration.idle.run_once()
    prompt = await integration.idle.current_prompt(mapped)
    assert (
        await integration.idle.cancel_current(
            ControlContext(mapped, 42, prompt_id=prompt.prompt_id, operation_id="cancel")
        )
    ).accepted
    record = await integration.idle.inspect(mapped)
    assert record.idle.phase is Phase.EFFECT_UNKNOWN and business.calls == 1
    # Even an explicit administrative retry of the outer aggregate cannot
    # reinterpret an uncertain inner business call as definitely unsent.
    clock.advance(1)
    record = await integration.idle.backend.transition(
        mapped,
        expected_version=record.version,
        operation_id="operator-retry",
        fingerprint="operator-retry",
        transform=lambda old: replace(
            old, idle=replace(old.idle, phase=Phase.ABANDONING, deadline=clock.now())
        ),
    )
    async with integration.idle.coordinator.hold(mapped):
        await integration.idle.worker.execute(record, None)
    assert business.calls == 1
    assert (await integration.idle.inspect(mapped)).idle.phase is Phase.EFFECT_UNKNOWN
