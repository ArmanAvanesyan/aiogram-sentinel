"""Crash windows retain known receipts and never blindly repeat uncertain sends."""

import asyncio

import pytest

from aiogram_nav.effects import NavigationEffects
from aiogram_nav.errors import (
    AccessDenied,
    OperationIdConflict,
    OperationPending,
    OwnershipLost,
    PersistenceUnavailable,
    RenderUnknown,
    SessionExpired,
    StaleView,
)
from aiogram_nav.models import MessageRef, RenderResult, ViewState
from aiogram_nav.rendering.base import CleanupResult
from tests.test_navigation import KEY, harness


class StagedPresenter:
    replay_safe = True

    def __init__(self):
        self.sends = 0
        self.interrupt = True

    async def render(self, request):
        async def send():
            self.sends += 1
            return {"message_id": 99}

        receipt = await request.effects.run("message", send)
        if self.interrupt:
            self.interrupt = False
            raise RuntimeError("lost outer result after known inner receipt")
        return RenderResult(
            request.view_id, (MessageRef(request.key.chat_id, receipt["message_id"]),)
        )

    async def cleanup(self, request):
        return CleanupResult()


async def test_prepare_failure_performs_no_render(monkeypatch):
    nav, ctx, presenter, _ = harness()

    async def fail(*args, **kwargs):
        raise PersistenceUnavailable("prepare unavailable")

    monkeypatch.setattr(nav.repository, "prepare", fail)
    with pytest.raises(PersistenceUnavailable):
        await ctx.go("main", operation_id="go")
    assert presenter.requests == []


async def test_render_failure_preserves_old_committed_screen_and_uncertain_evidence():
    nav, ctx, presenter, _ = harness()
    await ctx.go("main", operation_id="main")
    presenter.failure = TimeoutError("response lost after send")
    with pytest.raises(RenderUnknown):
        await ctx.go("a", operation_id="a")
    assert (await ctx.current()).node_id == "main"
    pending = await nav.pending(KEY)
    assert pending.effects["render"].state == "unknown"
    presenter.failure = None
    with pytest.raises(RenderUnknown):
        await ctx.go("a", operation_id="a")
    with pytest.raises(OperationPending):
        await ctx.go("b", operation_id="b")
    assert len(presenter.requests) == 2
    await ctx.refresh(operation_id="explicit-refresh")
    assert (await ctx.current()).node_id == "main"
    assert (await nav.repository.lookup_operation(KEY, operation_id="a")).status == "failed"


async def test_confirmed_nested_send_recovery_reconstructs_without_duplicate_send():
    nav, ctx, _, _ = harness()
    presenter = StagedPresenter()
    nav.presenter = presenter
    with pytest.raises(RenderUnknown):
        await ctx.go("main", operation_id="go")
    assert await ctx.current() is None
    result = await nav.recover(KEY, operation_id="go")
    assert result.messages == (MessageRef(2, 99),) and presenter.sends == 1
    assert (await ctx.current()).node_id == "main"


async def test_confirmed_render_survives_later_commit_failure(monkeypatch):
    nav, ctx, presenter, _ = harness()
    commit = nav.repository.commit

    async def fail(*args, **kwargs):
        raise PersistenceUnavailable("completion unavailable")

    monkeypatch.setattr(nav.repository, "commit", fail)
    with pytest.raises(PersistenceUnavailable):
        await ctx.go("main", operation_id="go")
    assert await ctx.current() is None
    monkeypatch.setattr(nav.repository, "commit", commit)
    await nav.recover(KEY, operation_id="go")
    assert len(presenter.requests) == 1
    assert (await ctx.current()).node_id == "main"


async def test_cancel_hook_confirmation_survives_later_render_failure():
    calls = []

    async def cancel(request):
        calls.append(request.operation_id)
        return {"abandoned": True}

    nav, ctx, presenter, _ = harness(cancel_hook=cancel)
    await ctx.go("a", operation_id="a")
    staged = StagedPresenter()
    nav.presenter = staged
    with pytest.raises(RenderUnknown):
        await ctx.cancel(operation_id="cancel")
    await nav.recover(KEY, operation_id="cancel")
    assert calls == ["cancel"] and staged.sends == 1
    assert (await ctx.current()).node_id == "main"


async def test_unknown_business_cancellation_cannot_be_erased_by_refresh():
    async def cancel(request):
        raise TimeoutError("business response lost")

    nav, ctx, _, _ = harness(cancel_hook=cancel)
    await ctx.go("a", operation_id="a")
    with pytest.raises(RenderUnknown):
        await ctx.cancel(operation_id="cancel")
    with pytest.raises(RenderUnknown):
        await ctx.refresh(operation_id="refresh")
    assert (await nav.pending(KEY)).operation_id == "cancel"


async def test_late_confirmed_receipt_is_retained_without_expired_location_commit():
    nav, ctx, presenter, clock = harness()
    original = presenter.render

    async def late(request):
        clock.advance(100001)
        return await original(request)

    presenter.render = late
    with pytest.raises(SessionExpired):
        await ctx.go("main", operation_id="late")
    status = await nav.repository.lookup_operation(KEY, operation_id="late")
    assert status.prepared.effects["render"].state == "confirmed"
    assert await ctx.current() is None


async def test_stale_recorder_and_wrong_conversation_completion_rejected():
    nav, ctx, _, _ = harness()
    prepared = await ctx.prepare_render("main", operation_id="prepared")
    async with nav.coordinator.hold(KEY):
        recorder = NavigationEffects(nav, prepared)
    with pytest.raises(OwnershipLost):
        await recorder.run("late", lambda: asyncio.sleep(0))
    with pytest.raises(StaleView):
        await ctx.complete_render(
            prepared, rendered=RenderResult(prepared.view_id, (MessageRef(3, 9),))
        )
    with pytest.raises(RenderUnknown):
        await ctx.complete_render(
            prepared, rendered=ViewState(prepared.view_id, render_status="partial")
        )


async def test_cancellation_preserves_request_started_for_explicit_recovery():
    nav, ctx, presenter, _ = harness()
    entered = asyncio.Event()

    async def wait(request):
        entered.set()
        await asyncio.Event().wait()

    presenter.render = wait
    task = asyncio.create_task(ctx.go("main", operation_id="cancelled"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    pending = await nav.pending(KEY)
    assert pending.effects["render"].state in {"started", "unknown"}
    with pytest.raises(RenderUnknown):
        await nav.recover(KEY, operation_id="cancelled")


async def test_delegated_parallel_effects_share_live_scope_but_not_handler_ownership():
    nav, ctx, _, _ = harness()
    prepared = await ctx.prepare_render("main", operation_id="prepared")
    async with nav.coordinator.hold(KEY):
        effects = NavigationEffects(nav, prepared)
        calls = []

        async def child(stage):
            assert nav.coordinator.scope_token(KEY) is None

            async def effect():
                calls.append(stage)
                return {"stage": stage}

            return await effects.run(stage, effect)

        results = await asyncio.gather(child("one"), child("two"))
        assert [result["stage"] for result in results] == ["one", "two"]
        assert calls == ["one", "two"]
    with pytest.raises(OwnershipLost):
        await effects.record()


async def test_touch_operation_id_cannot_be_reused_for_go_or_other_source():
    _, ctx, _, _ = harness()
    await ctx.go("main", operation_id="go")
    with pytest.raises(OperationIdConflict):
        await ctx.touch(operation_id="go")
    await ctx.touch(operation_id="touch", source="typing")
    with pytest.raises(OperationIdConflict):
        await ctx.touch(operation_id="touch", source="another")


async def test_forged_prepared_intent_cannot_authorize_a_different_canonical_target():
    from dataclasses import replace

    permitted = True

    async def authorize(key, node, params, source):
        return node.id != "a" or permitted

    nav, ctx, _, _ = harness(authorize=authorize)
    prepared = await ctx.prepare_render("a", operation_id="private")
    permitted = False
    forged = replace(prepared, intent=replace(prepared.intent, node_id="main"))
    with pytest.raises(StaleView):
        await ctx.complete_render(forged, rendered=RenderResult(prepared.view_id))
    with pytest.raises(AccessDenied):
        await ctx.complete_render(prepared, rendered=RenderResult(prepared.view_id))
    assert await ctx.current() is None
    assert (await nav.pending(KEY)).node_id == "a"


async def test_denied_refresh_does_not_abandon_an_unresolved_render():
    permitted = True

    async def authorize(key, node, params, source):
        return permitted

    nav, ctx, presenter, _ = harness(authorize=authorize)
    await ctx.go("main", operation_id="main")
    presenter.failure = TimeoutError()
    with pytest.raises(RenderUnknown):
        await ctx.go("a", operation_id="pending")
    permitted = False
    with pytest.raises(AccessDenied):
        await ctx.refresh(operation_id="denied-refresh")
    assert (await nav.pending(KEY)).operation_id == "pending"
