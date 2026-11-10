"""Cross-module regressions found during independent contract review."""

from dataclasses import replace

import pytest

from aiogram_nav.errors import AccessDenied, OperationIdConflict, RenderUnknown, StaleView
from aiogram_nav.models import MessageRef, RenderResult
from tests.test_navigation import KEY, harness


async def test_background_navigation_preserves_accepted_activity_time():
    _, ctx, _, clock = harness()
    await ctx.go("main", operation_id="main")
    old = await ctx.current()
    clock.advance(500)
    await ctx.go("a", operation_id="background", source="background", accepted_activity=False)
    current = await ctx.current()
    assert current.entered_at == 1500
    assert current.last_activity_at == old.last_activity_at == 1000
    assert current.activity_revision == old.activity_revision
    assert current.expires_at == old.expires_at


async def test_caller_cannot_authorize_forged_intent_while_committing_private_reservation():
    allow_private = True

    async def authorize(key, node, params, source):
        return node.id != "a" or allow_private

    nav, ctx, _, _ = harness(authorize=authorize)
    await ctx.go("main", operation_id="main")
    prepared = await ctx.prepare_render("a", operation_id="manual")
    allow_private = False
    forged = replace(prepared, intent=replace(prepared.intent, node_id="main"))
    result = RenderResult(prepared.view_id, (MessageRef(KEY.chat_id, 99),))
    with pytest.raises((AccessDenied, StaleView, OperationIdConflict)):
        await ctx.complete_render(forged, rendered=result)
    assert (await ctx.current()).node_id == "main"
    assert (await nav.pending(KEY)).operation_id == "manual"


async def test_denied_refresh_does_not_erase_pending_recovery_evidence():
    allowed = True

    async def authorize(key, node, params, source):
        return allowed

    nav, ctx, presenter, _ = harness(authorize=authorize)
    await ctx.go("main", operation_id="main")
    presenter.failure = TimeoutError("uncertain response")
    with pytest.raises(RenderUnknown):
        await ctx.go("a", operation_id="uncertain")
    pending = await nav.pending(KEY)
    presenter.failure = None
    allowed = False
    with pytest.raises(AccessDenied):
        await ctx.refresh(operation_id="denied-refresh")
    assert await nav.pending(KEY) == pending


@pytest.mark.parametrize("changed", [True, 1.0])
async def test_operation_retry_distinguishes_json_booleans_and_numbers(changed):
    _, ctx, _, _ = harness()
    await ctx.go("a", params={"value": 1}, operation_id="typed-int")
    with pytest.raises(OperationIdConflict):
        await ctx.go("a", params={"value": changed}, operation_id="typed-int")
