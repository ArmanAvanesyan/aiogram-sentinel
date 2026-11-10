"""Bound retained metadata and preserve callback view generations."""

from dataclasses import replace

import pytest

from aiogram_nav.clock import ManualClock
from aiogram_nav.config import NavigationConfig
from aiogram_nav.errors import OperationIdConflict, Overloaded, StaleView
from aiogram_nav.models import (
    ConversationKey,
    EffectCheckpoint,
    NavigationAction,
    NavigationIntent,
    NavigationMutation,
    NavigationToken,
    RenderResult,
)
from aiogram_nav.storage.memory import MemoryNavigationRepository

KEY = ConversationKey("audit", 1, 2, 2)


async def test_stage_limit_rejects_admission_without_erasing_started_evidence():
    repo = MemoryNavigationRepository(
        clock=ManualClock(1000), config=NavigationConfig(max_receipts=2)
    )
    await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("render", "root"))
    first = EffectCheckpoint("send-one", "started")
    await repo.checkpoint(KEY, operation_id="render", effect=first)
    await repo.checkpoint(
        KEY, operation_id="render", effect=EffectCheckpoint("send-two", "started")
    )
    before = await repo.pending(KEY)
    with pytest.raises(Overloaded):
        await repo.checkpoint(
            KEY, operation_id="render", effect=EffectCheckpoint("send-three", "started")
        )
    assert await repo.pending(KEY) == before
    assert (
        await repo.checkpoint(KEY, operation_id="render", effect=first)
    ).effects == before.effects
    await repo.checkpoint(
        KEY, operation_id="render", effect=EffectCheckpoint("send-one", "confirmed", True)
    )
    assert (await repo.pending(KEY)).effects["send-two"].state == "started"


@pytest.mark.parametrize(
    "payload", ["x" * 100, ["x"] * 100, {"data": "x" * 100}, RenderResult("v" * 100)]
)
async def test_oversized_receipt_is_rejected_without_false_confirmation(payload):
    repo = MemoryNavigationRepository(
        clock=ManualClock(1000), config=NavigationConfig(max_params_bytes=64)
    )
    await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("render", "root"))
    await repo.checkpoint(KEY, operation_id="render", effect=EffectCheckpoint("send", "started"))
    before = await repo.pending(KEY)
    with pytest.raises(Overloaded):
        await repo.checkpoint(
            KEY, operation_id="render", effect=EffectCheckpoint("send", "confirmed", payload)
        )
    assert await repo.pending(KEY) == before
    assert (await repo.pending(KEY)).effects["send"].state == "started"


async def test_reused_raw_token_cannot_alias_two_reservation_operation_ids():
    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "root")
    )
    token = NavigationToken(
        "opaque",
        KEY,
        2,
        prepared.session_id,
        prepared.view_id,
        NavigationAction(target="other"),
        prepared.expires_at,
    )
    await repo.reserve_token(KEY, token, operation_id="token-one")
    with pytest.raises(OperationIdConflict):
        await repo.reserve_token(KEY, token, operation_id="token-two")
    other = replace(token, token="other-opaque", action=NavigationAction(target="different"))
    assert await repo.reserve_token(KEY, other, operation_id="token-two") == other
    with pytest.raises(OperationIdConflict):
        await repo.reserve_token(KEY, replace(other, action=token.action), operation_id="token-two")
    assert (
        await repo.reserve_token(
            KEY, replace(token, token="random-retry"), operation_id="token-one"
        )
        == token
    )


async def test_track_cannot_reanimate_current_or_retained_previous_view_tokens():
    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    first = await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("first", "root"))
    result = await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("first", first.session_id, RenderResult(first.view_id)),
    )
    reused = NavigationIntent("track", "different", action="track", view_id=first.view_id)
    with pytest.raises(StaleView):
        await repo.prepare(KEY, expected_version=result.version, intent=reused)
    second = await repo.prepare(
        KEY, expected_version=result.version, intent=NavigationIntent("second", "other")
    )
    result = await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("second", second.session_id, RenderResult(second.view_id)),
    )
    with pytest.raises(StaleView):
        await repo.prepare(KEY, expected_version=result.version, intent=reused)
    # Retrying the original prepared action still deduplicates before generation checks.
    assert (
        await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("first", "root"))
    ).view_id == first.view_id


async def test_repeated_views_prune_active_tokens_but_keep_bounded_action_evidence():
    repo = MemoryNavigationRepository(
        clock=ManualClock(1000), config=NavigationConfig(max_tokens=2, max_receipts=32)
    )
    first_token = None
    for index in range(10):
        current = await repo.load(KEY)
        prepared = await repo.prepare(
            KEY,
            expected_version=current.version if current else None,
            intent=NavigationIntent(f"render-{index}", "root"),
        )
        token = NavigationToken(
            f"token-{index}",
            KEY,
            2,
            prepared.session_id,
            prepared.view_id,
            NavigationAction(target="other"),
            prepared.expires_at,
        )
        await repo.reserve_token(KEY, token, operation_id=f"reserve-{index}")
        await repo.commit(
            KEY,
            expected_version=None,
            mutation=NavigationMutation(
                prepared.operation_id, prepared.session_id, RenderResult(prepared.view_id)
            ),
        )
        assert len(repo._records[KEY].tokens) == 1
        assert all(
            len(entry.token_receipts) <= 2 for entry in repo._records[KEY].operations.values()
        )
        first_token = first_token or token
    assert await repo.resolve_token(KEY, first_token.token) is None
    # Old reservation retries remain idempotent metadata; they never reactivate it.
    assert await repo.reserve_token(KEY, first_token, operation_id="reserve-0") == first_token
    assert len(repo._records[KEY].tokens) == 1
    with pytest.raises(OperationIdConflict):
        await repo.reserve_token(KEY, replace(token, token="new-token"), operation_id="reserve-0")


async def test_consumption_operation_cannot_alias_different_controls():
    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "root")
    )
    one = NavigationToken(
        "one",
        KEY,
        2,
        prepared.session_id,
        prepared.view_id,
        NavigationAction(target="first"),
        prepared.expires_at,
    )
    two = replace(one, token="two", action=NavigationAction(target="second"))
    await repo.reserve_token(KEY, one, operation_id="reserve-one")
    await repo.reserve_token(KEY, two, operation_id="reserve-two")
    await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("render", prepared.session_id, RenderResult(prepared.view_id)),
    )
    await repo.consume_token(KEY, "one", actor_id=2, operation_id="action")
    with pytest.raises(OperationIdConflict):
        await repo.consume_token(KEY, "two", actor_id=2, operation_id="action")
    assert await repo.consume_token(KEY, "one", actor_id=2, operation_id="action") == one


@pytest.mark.parametrize("before,after", [(1, True), (1, 1.0), (1.0, True)])
async def test_checkpoint_fingerprints_distinguish_json_boolean_integer_and_float(before, after):
    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("render", "root"))
    await repo.checkpoint(KEY, operation_id="render", effect=EffectCheckpoint("send", "started"))
    await repo.checkpoint(
        KEY, operation_id="render", effect=EffectCheckpoint("send", "confirmed", before)
    )
    with pytest.raises(OperationIdConflict):
        await repo.checkpoint(
            KEY, operation_id="render", effect=EffectCheckpoint("send", "confirmed", after)
        )


@pytest.mark.parametrize("before,after", [(1, True), (1, 1.0), (1.0, True)])
async def test_parameter_type_changes_push_history_and_reset_entry_time(before, after):
    clock = ManualClock(1000)
    repo = MemoryNavigationRepository(clock=clock)
    prepared = await repo.prepare(
        KEY,
        expected_version=None,
        intent=NavigationIntent("first", "root", params={"value": before}),
    )
    result = await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("first", prepared.session_id, RenderResult(prepared.view_id)),
    )
    clock.advance(10)
    prepared = await repo.prepare(
        KEY,
        expected_version=result.version,
        intent=NavigationIntent("second", "root", params={"value": after}),
    )
    result = await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("second", prepared.session_id, RenderResult(prepared.view_id)),
    )
    assert result.snapshot.entered_at == 1010
    assert len(result.snapshot.history) == 1
    assert type(result.snapshot.history[0].params["value"]) is type(before)
    assert type(result.snapshot.params["value"]) is type(after)
