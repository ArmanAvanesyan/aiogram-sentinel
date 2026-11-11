"""Application-owned routing and rendering retain navigation safety boundaries."""

import asyncio

import pytest
from aiogram import F, Router
from aiogram.types import CallbackQuery, Update

from aiogram_nav import (
    ApplicationPresenter,
    CleanupResult,
    ConfigurationError,
    ConversationKey,
    InputBindings,
    MessageRef,
    Navigation,
    RenderResult,
    ReplyEntry,
    create_bindings_router,
)
from tests.test_dispatcher import harness
from tests.test_examples import ACTOR, incoming
from tests.test_navigation import KEY
from tests.test_navigation import harness as action_harness


async def test_state_guard_precedes_manual_reply_binding():
    dp, nav, bot, _ = harness(
        bindings=InputBindings(
            [ReplyEntry("panel", text_key="Panel", target="panel", global_action=True)]
        )
    )
    guard = Router()
    calls = []

    @guard.message(F.text == "Panel")
    async def guarded(message):
        calls.append("guard")

    router = create_bindings_router(nav)
    dp.include_router(guard)
    dp.include_router(router)
    nav.install(dp, bindings_mode="manual", bindings_router=router)
    try:
        await dp.feed_update(bot, Update(update_id=1, message=incoming("Panel")))
        assert calls == ["guard"]
        assert (
            await nav.for_conversation(ConversationKey("default", bot.id, 42, 42)).current() is None
        )
        assert dp.sub_routers == [guard, router]
    finally:
        await dp.fsm.close()
        await bot.session.close()


async def test_manual_root_handler_is_explicit_and_stale_callback_cannot_reach_it():
    dp, nav, bot, _ = harness(
        bindings=InputBindings([ReplyEntry("panel", text_key="Panel", target="panel")])
    )
    calls = []
    rejected = []

    @dp.callback_query()
    async def root(callback):
        calls.append(callback.data)

    async def reject(request):
        rejected.append(request.reason)

    nav.callback_rejection = reject
    router = create_bindings_router(nav)
    dp.include_router(router)
    with pytest.raises(ConfigurationError):
        nav.install(dp, bindings_mode="manual", bindings_router=router)
    nav.install(dp, bindings_mode="manual", bindings_router=router, allow_root_handlers=True)
    try:
        await dp.feed_update(
            bot,
            Update(
                update_id=1,
                callback_query=CallbackQuery(
                    id="stale",
                    from_user=ACTOR,
                    chat_instance="chat",
                    message=incoming("screen"),
                    data="nav:unknown",
                ),
            ),
        )
        assert calls == [] and rejected == ["stale"]
    finally:
        await dp.fsm.close()
        await bot.session.close()


async def test_prepared_back_cancel_and_cleanup_have_one_application_owner():
    original, _, _, clock = action_harness()
    cleanups = []
    cancellations = []

    async def cleanup(request):
        request.ensure_owned()
        cleanups.append(request)
        return CleanupResult()

    async def cancel(request):
        cancellations.append(request.node.id)
        return None

    nav = Navigation(
        registry=original.registry,
        repository=original.repository,
        presenter=ApplicationPresenter(cleanup=cleanup),
        cancel_hook=cancel,
    )
    ctx = nav.for_conversation(KEY)

    async def render(kind, **kwargs):
        prepared = await ctx.prepare_action(kind, **kwargs)
        return await ctx.complete_render(
            prepared,
            rendered=RenderResult(prepared.view_id, (MessageRef(KEY.chat_id, len(cleanups) + 1),)),
        )

    with pytest.raises(ConfigurationError, match="prepare_action"):
        await ctx.go("main", operation_id="automatic")
    assert await nav.pending(KEY) is None
    await render("go", node_id="main", operation_id="main")
    await render("go", node_id="a", operation_id="a")
    await render("go", node_id="b", operation_id="b")
    assert (await render("back", operation_id="back")).node_id == "a"
    assert (await render("cancel", operation_id="cancel")).node_id == "main"
    assert cancellations == ["main"]
    assert len(cleanups) == 5
    prepared = (await nav.repository.lookup_operation(KEY, operation_id="cancel")).prepared
    await ctx.complete_render(
        prepared, rendered=RenderResult(prepared.view_id, (MessageRef(KEY.chat_id, 5),))
    )
    assert len(cleanups) == 5 and cancellations == ["main"]


async def test_drain_times_out_without_releasing_an_owned_scope():
    nav, ctx, _, _ = action_harness()
    entered, release = asyncio.Event(), asyncio.Event()

    async def busy():
        async with nav.coordinator.hold(KEY):
            entered.set()
            await release.wait()

    task = asyncio.create_task(busy())
    await entered.wait()
    try:
        with pytest.raises(TimeoutError):
            await nav.drain(timeout_seconds=0.02)
        assert nav.coordinator.active_scopes == 1
        with pytest.raises(ConfigurationError, match="draining"):
            await ctx.go("main", operation_id="blocked")
    finally:
        release.set()
        await task
    await nav.drain()


async def test_previously_admitted_scope_can_finish_during_drain():
    nav, ctx, _, _ = action_harness()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def handler():
        async with nav.coordinator.hold(KEY):
            entered.set()
            await finish.wait()
            await ctx.go("main", operation_id="finish-existing")

    task = asyncio.create_task(handler())
    await entered.wait()
    draining = asyncio.create_task(nav.drain(timeout_seconds=2))
    await asyncio.sleep(0)
    assert nav.draining and not draining.done()
    finish.set()
    await asyncio.gather(task, draining)
    assert (await ctx.current()).node_id == "main"


async def test_application_presenter_delegates_render_and_cleanup_once():
    original, _, _, _ = action_harness()
    calls = []

    async def render(request):
        await request.effects.record()
        calls.append(("render", request.node_id))
        return RenderResult(request.view_id, (MessageRef(KEY.chat_id, len(calls)),))

    async def cleanup(request):
        request.ensure_owned()
        calls.append(("cleanup", request.current is not None))
        return CleanupResult()

    nav = Navigation(
        registry=original.registry,
        repository=original.repository,
        presenter=ApplicationPresenter(render=render, cleanup=cleanup),
    )
    context = nav.for_conversation(KEY)
    await context.go("main", operation_id="one")
    await context.go("main", operation_id="one")
    assert calls == [("render", "main"), ("cleanup", True)]
