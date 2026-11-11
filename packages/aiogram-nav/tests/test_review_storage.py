"""Regression coverage from the pre-Redis storage/ownership review."""

from dataclasses import replace

import pytest

from aiogram_nav import (
    EffectCheckpoint,
    ManualClock,
    MemoryNavigationRepository,
    MessageRef,
    NavigationAction,
    NavigationConfig,
    NavigationIntent,
    NavigationMutation,
    NavigationSnapshot,
    NavigationToken,
    OperationIdConflict,
    RenderResult,
    VersionedSnapshot,
    ViewState,
)
from tests.test_storage import KEY, enter


async def test_completion_cannot_replace_a_confirmed_render_receipt():
    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "root")
    )
    delivered = RenderResult(prepared.view_id, (MessageRef(KEY.chat_id, 10),))
    await repo.checkpoint(KEY, operation_id="render", effect=EffectCheckpoint("render", "started"))
    await repo.checkpoint(
        KEY, operation_id="render", effect=EffectCheckpoint("render", "confirmed", delivered)
    )
    forged = replace(delivered, messages=(MessageRef(KEY.chat_id, 11),))
    before = await repo.pending(KEY)
    with pytest.raises(OperationIdConflict):
        await repo.commit(
            KEY,
            expected_version=None,
            mutation=NavigationMutation("render", prepared.session_id, forged),
        )
    assert await repo.pending(KEY) == before
    assert await repo.load(KEY) is None
    result = await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("render", prepared.session_id, delivered),
    )
    assert result.snapshot.view.messages == delivered.messages


async def test_submillisecond_positive_intervals_round_up_instead_of_expiring_immediately():
    repo = MemoryNavigationRepository(
        clock=ManualClock(1000),
        config=NavigationConfig(session_seconds=0.0001, recovery_seconds=0.0001),
    )
    prepared, result = await enter(repo)
    assert prepared.expires_at == 1001
    assert result.snapshot.expires_at == 1001
    assert (await repo.lookup_operation(KEY, operation_id="enter")).status == "completed"
    duplicate = await repo.commit(
        KEY,
        expected_version="old",
        mutation=NavigationMutation("enter", prepared.session_id, RenderResult(prepared.view_id)),
    )
    assert duplicate.duplicate
    repo.clock.advance(1)
    assert await repo.load(KEY) is None
    assert (await repo.lookup_operation(KEY, operation_id="enter")).status == "not_found"


@pytest.mark.parametrize("last_seen", [2000, 2001])
def test_snapshot_rejects_activity_at_or_beyond_absolute_expiry(last_seen):
    with pytest.raises(ValueError):
        NavigationSnapshot("session", "root", {}, 1, 1, 1000, last_seen, 2000, ViewState("view"))


def test_background_snapshot_still_allows_earlier_last_activity():
    snapshot = NavigationSnapshot("session", "root", {}, 1, 1, 1500, 1000, 2000, ViewState("view"))
    assert snapshot.last_activity_at < snapshot.entered_at


@pytest.mark.parametrize("actor", [2.0, True, "2", None])
async def test_control_actor_requires_an_integer_identity(actor):
    from aiogram_nav import NavigationAction, NavigationToken, StaleView

    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    prepared, _ = await enter(repo)
    token = NavigationToken(
        "control",
        KEY,
        KEY.user_id,
        prepared.session_id,
        prepared.view_id,
        NavigationAction(target="other"),
        prepared.expires_at,
    )
    await repo.reserve_token(KEY, token, operation_id="reserve")
    with pytest.raises(StaleView):
        await repo.consume_token(KEY, "control", actor_id=actor, operation_id="consume")
    assert (
        await repo.consume_token(KEY, "control", actor_id=KEY.user_id, operation_id="consume")
        == token
    )


@pytest.mark.parametrize("interval", [1e308, 10**1000])
@pytest.mark.parametrize("field", ["session_seconds", "recovery_seconds"])
def test_unrepresentable_millisecond_interval_fails_configuration(field, interval):
    from aiogram_nav import ConfigurationError

    with pytest.raises(ConfigurationError):
        NavigationConfig(**{field: interval})


async def test_complete_view_subtype_is_a_semantically_identical_receipt():
    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "root")
    )
    rendered = ViewState(prepared.view_id, (MessageRef(KEY.chat_id, 10),))
    await repo.checkpoint(KEY, operation_id="render", effect=EffectCheckpoint("render", "started"))
    await repo.checkpoint(
        KEY, operation_id="render", effect=EffectCheckpoint("render", "confirmed", rendered)
    )
    plain = RenderResult(rendered.view_id, rendered.messages)
    first = await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("render", prepared.session_id, plain),
    )
    duplicate = await repo.commit(
        KEY,
        expected_version="stale",
        mutation=NavigationMutation("render", prepared.session_id, rendered),
    )
    assert duplicate.duplicate and duplicate.snapshot == first.snapshot


@pytest.mark.parametrize(
    "factory",
    [
        lambda: NavigationMutation("op", "session", rendered={}),
        lambda: VersionedSnapshot({}, "version"),
        lambda: NavigationToken("token", {}, 2, "session", "view", NavigationAction(), 5000),
    ],
)
def test_structured_contract_fields_reject_wrong_types_at_boundary(factory):
    with pytest.raises(ValueError):
        factory()


async def test_prepared_effect_map_rejects_non_checkpoint_values():
    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "root")
    )
    with pytest.raises(ValueError):
        replace(prepared, effects={"send": "invalid"})
