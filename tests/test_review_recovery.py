"""Review regressions at stage-execution and authorization boundaries."""

import asyncio

import pytest

from aiogram_nav.effects import NavigationEffects
from aiogram_nav.errors import AccessDenied, InvalidParameters, RenderUnknown
from aiogram_nav.models import MessageRef, Node
from aiogram_nav.navigation import Navigation
from tests.test_navigation import KEY, harness


async def test_independent_recorders_cannot_execute_the_same_stage_twice():
    nav, ctx, _, _ = harness()
    prepared = await ctx.prepare_render("main", operation_id="prepared")
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async with nav.coordinator.hold(KEY):
        first = NavigationEffects(nav, prepared)
        second = NavigationEffects(nav, prepared)

        async def send():
            calls.append("send")
            entered.set()
            await release.wait()
            return {"message_id": 7}

        one = asyncio.create_task(first.run("same-send", send))
        await entered.wait()
        two = asyncio.create_task(second.run("same-send", send))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert calls == ["send"]
        release.set()
        results = await asyncio.wait_for(asyncio.gather(one, two), timeout=5)
        assert results == [{"message_id": 7}, {"message_id": 7}]
        assert calls == ["send"]


async def test_recorders_share_execution_guards_across_runtimes():
    nav, ctx, presenter, _ = harness()
    other = Navigation(registry=nav.registry, repository=nav.repository, presenter=presenter)
    prepared = await ctx.prepare_render("main", operation_id="prepared")
    async with nav.coordinator.hold(KEY):
        first, second = NavigationEffects(nav, prepared), NavigationEffects(other, prepared)
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def send():
            calls.append(1)
            entered.set()
            await release.wait()
            return True

        one = asyncio.create_task(first.run("message", send))
        await entered.wait()
        two = asyncio.create_task(second.run("message", send))
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(asyncio.gather(one, two), timeout=5)
        assert calls == [1]


async def test_cross_recorder_recursive_stage_rejected_without_deadlock():
    nav, ctx, _, _ = harness()
    prepared = await ctx.prepare_render("main", operation_id="prepared")
    async with nav.coordinator.hold(KEY):
        first, second = NavigationEffects(nav, prepared), NavigationEffects(nav, prepared)

        async def recurse():
            return await second.run("same", lambda: asyncio.sleep(0))

        with pytest.raises(RenderUnknown):
            await asyncio.wait_for(first.run("same", recurse), timeout=5)


async def test_permission_revoked_during_intent_checkpoint_prevents_effect(monkeypatch):
    permitted = True

    async def authorize(key, node, params, source):
        return permitted

    nav, ctx, presenter, _ = harness(authorize=authorize)
    original = nav.repository.checkpoint

    async def revoke(key, *, operation_id, effect, **kwargs):
        nonlocal permitted
        saved = await original(key, operation_id=operation_id, effect=effect, **kwargs)
        if effect.stage == "render" and effect.state == "started":
            permitted = False
        return saved

    monkeypatch.setattr(nav.repository, "checkpoint", revoke)
    with pytest.raises(AccessDenied):
        await ctx.go("main", operation_id="denied")
    assert presenter.requests == []
    pending = await nav.pending(KEY)
    assert pending.effects["render"].state == "not_sent"
    assert await ctx.current() is None


async def test_validator_cannot_reinterpret_prepared_reconstruction_parameters():
    version = [1]

    def validator(params):
        return {**params, "version": version[0]}

    nav, ctx, presenter, _ = harness(nodes=[Node("main", renderer="main", validator=validator)])
    prepared = await ctx.prepare_render("main", operation_id="prepared")
    version[0] = 2
    with pytest.raises(InvalidParameters):
        await nav.recover(KEY, operation_id=prepared.operation_id)
    assert presenter.requests == []


async def test_complete_view_receipt_has_stable_duplicate_semantics():
    from aiogram_nav.models import ViewState

    nav, ctx, presenter, _ = harness()
    prepared = await ctx.prepare_render("main", operation_id="manual")
    rendered = ViewState(prepared.view_id, (MessageRef(KEY.chat_id, 99),))
    first = await ctx.complete_render(prepared, rendered=rendered)
    duplicate = await ctx.complete_render(prepared, rendered=rendered)
    assert duplicate == first
    assert presenter.requests == []


async def test_permission_denial_does_not_erase_an_older_uncertain_stage():
    permitted = True

    async def authorize(key, node, params, source):
        return permitted

    nav, ctx, _, _ = harness(authorize=authorize)
    prepared = await ctx.prepare_render("main", operation_id="manual")
    async with nav.coordinator.hold(KEY):
        effects = NavigationEffects(nav, prepared)
        await effects.checkpoint("message", "started")
        await effects.checkpoint("message", "unknown")
        permitted = False
        with pytest.raises(AccessDenied):
            await effects.run("message", lambda: asyncio.sleep(0), replay_safe=True)
        assert (await effects.record()).effects["message"].state == "unknown"


async def test_cancelled_stage_waiter_does_not_leak_shared_execution_guards():
    import aiogram_nav.effects as effects_module

    nav, ctx, _, _ = harness()
    prepared = await ctx.prepare_render("main", operation_id="manual")
    async with nav.coordinator.hold(KEY):
        first, second = NavigationEffects(nav, prepared), NavigationEffects(nav, prepared)
        entered, release = asyncio.Event(), asyncio.Event()

        async def send():
            entered.set()
            await release.wait()
            return True

        one = asyncio.create_task(first.run("message", send))
        await entered.wait()
        waiting = asyncio.create_task(second.run("message", send))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        release.set()
        await one
    assert not effects_module._stages


async def test_duplicate_action_cannot_alias_boolean_acceptance_with_integer():
    from aiogram_nav.errors import ConfigurationError

    _, ctx, _, _ = harness()
    await ctx.go("main", operation_id="first")
    with pytest.raises(ConfigurationError):
        await ctx.go("main", operation_id="first", accepted_activity=1)


async def test_rejected_safe_replay_does_not_disprove_an_older_started_attempt():
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import SendMessage

    nav, ctx, _, _ = harness()
    prepared = await ctx.prepare_render("main", operation_id="prepared")
    async with nav.coordinator.hold(KEY):
        effects = NavigationEffects(nav, prepared)
        await effects.checkpoint("message", "started")

        async def rejected():
            raise TelegramBadRequest(
                method=SendMessage(chat_id=KEY.chat_id, text="message"), message="rejected replay"
            )

        with pytest.raises(TelegramBadRequest):
            await effects.run("message", rejected, replay_safe=True)
        assert (await effects.record()).effects["message"].state == "started"
        calls = []

        async def resend():
            calls.append(1)
            return True

        with pytest.raises(RenderUnknown):
            await effects.run("message", resend)
        assert calls == []


async def test_child_copied_stage_marker_expires_when_parent_execution_finishes():
    nav, ctx, _, _ = harness()
    prepared = await ctx.prepare_render("main", operation_id="prepared")
    release = asyncio.Event()
    calls = []
    child_tasks = []
    async with nav.coordinator.hold(KEY):
        first, second = NavigationEffects(nav, prepared), NavigationEffects(nav, prepared)

        async def resend():
            calls.append("unexpected resend")
            return {"message_id": 9}

        async def child():
            await release.wait()
            return await second.run("message", resend)

        async def send():
            calls.append("first send")
            child_tasks.append(asyncio.create_task(child()))
            return {"message_id": 9}

        result = await first.run("message", send)
        release.set()
        assert await asyncio.wait_for(child_tasks[0], timeout=5) == result
        assert calls == ["first send"]
