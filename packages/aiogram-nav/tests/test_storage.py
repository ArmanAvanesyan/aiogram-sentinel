"""Memory navigation contracts: generations, receipts, claims and retention."""

import asyncio
from dataclasses import replace

import pytest

from aiogram_nav.clock import ManualClock
from aiogram_nav.config import NavigationConfig
from aiogram_nav.errors import (
    ConfigurationError,
    OperationIdConflict,
    Overloaded,
    OwnershipLost,
    PendingAction,
    RenderUnknown,
    SessionExpired,
    StaleView,
    VersionConflict,
)
from aiogram_nav.isolation import MemoryCoordinator
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

KEY = ConversationKey("test", 1, 2, 2)


def repository(**kwargs):
    return MemoryNavigationRepository(clock=ManualClock(1000), config=NavigationConfig(**kwargs))


async def enter(repo, node="root", op="enter", *, history="push", accepted=True):
    old = await repo.load(KEY)
    prepared = await repo.prepare(
        KEY,
        expected_version=old.version if old else None,
        intent=NavigationIntent(op, node, history=history, accepted_activity=accepted),
    )
    result = await repo.commit(
        KEY,
        expected_version=prepared.expected_version,
        mutation=NavigationMutation(
            op, prepared.session_id, RenderResult(prepared.view_id), accepted_activity=accepted
        ),
    )
    return prepared, result


async def test_prepare_never_commits_target_and_completion_advances_revisions():
    repo = repository()
    first, result = await enter(repo)
    current = await repo.load(KEY)
    assert current.snapshot == result.snapshot
    second = await repo.prepare(
        KEY,
        expected_version=current.version,
        intent=NavigationIntent("second", "other", params={"page": 2}),
    )
    pending = await repo.load(KEY)
    assert pending.snapshot.node_id == "root"
    assert pending.version != current.version
    assert (await repo.pending(KEY)).view_id == second.view_id
    completed = await repo.commit(
        KEY,
        expected_version=current.version,
        mutation=NavigationMutation("second", first.session_id, RenderResult(second.view_id)),
    )
    assert completed.snapshot.node_id == "other"
    assert completed.snapshot.nav_revision == 2
    assert completed.snapshot.activity_revision == 2
    assert completed.snapshot.history[0].node_id == "root"


async def test_deduplicated_prepare_and_complete_precede_stale_version():
    repo = repository()
    prepared, result = await enter(repo)
    retried = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("enter", "root")
    )
    assert retried.session_id == prepared.session_id
    duplicate = await repo.commit(
        KEY,
        expected_version="obsolete",
        mutation=NavigationMutation("enter", prepared.session_id, RenderResult(prepared.view_id)),
    )
    assert duplicate.duplicate and duplicate.snapshot == result.snapshot
    assert (await repo.lookup_operation(KEY, operation_id="enter")).status == "completed"
    with pytest.raises(OperationIdConflict):
        await repo.prepare(
            KEY, expected_version=None, intent=NavigationIntent("enter", "different")
        )
    with pytest.raises(OperationIdConflict):
        await repo.commit(
            KEY,
            expected_version=None,
            mutation=NavigationMutation(
                "enter",
                prepared.session_id,
                RenderResult(prepared.view_id),
                accepted_activity=False,
            ),
        )


async def test_stale_versions_pending_action_and_view_guards():
    repo = repository()
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("first", "root")
    )
    with pytest.raises(PendingAction):
        await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("second", "other"))
    with pytest.raises(StaleView):
        await repo.commit(
            KEY,
            expected_version=None,
            mutation=NavigationMutation("first", prepared.session_id, RenderResult("wrong")),
        )
    with pytest.raises(SessionExpired):
        await repo.commit(
            KEY,
            expected_version=None,
            mutation=NavigationMutation("first", "wrong", RenderResult(prepared.view_id)),
        )
    await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("first", prepared.session_id, RenderResult(prepared.view_id)),
    )
    with pytest.raises(VersionConflict):
        await repo.prepare(KEY, expected_version="old", intent=NavigationIntent("new", "other"))


async def test_effect_ledger_rejects_unknown_and_reuses_confirmed_receipts():
    repo = repository()
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "root")
    )
    await repo.checkpoint(KEY, operation_id="render", effect=EffectCheckpoint("send", "started"))
    with pytest.raises(RenderUnknown):
        await repo.commit(
            KEY,
            expected_version=None,
            mutation=NavigationMutation(
                "render", prepared.session_id, RenderResult(prepared.view_id)
            ),
        )
    await repo.checkpoint(KEY, operation_id="render", effect=EffectCheckpoint("send", "unknown"))
    assert (await repo.lookup_operation(KEY, operation_id="render")).status == "unknown"
    with pytest.raises(RenderUnknown):
        await repo.checkpoint(
            KEY, operation_id="render", effect=EffectCheckpoint("send", "started")
        )
    confirmed = EffectCheckpoint("send", "confirmed", {"message_id": 42})
    await repo.checkpoint(KEY, operation_id="render", effect=confirmed)
    await repo.checkpoint(KEY, operation_id="render", effect=confirmed)
    with pytest.raises(OperationIdConflict):
        await repo.checkpoint(
            KEY, operation_id="render", effect=replace(confirmed, result={"message_id": 43})
        )
    await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("render", prepared.session_id, RenderResult(prepared.view_id)),
    )
    assert (await repo.lookup_operation(KEY, operation_id="render")).prepared.effects[
        "send"
    ] == confirmed


async def test_unknown_recovery_preserves_old_evidence_and_allows_explicit_new_action():
    repo = repository()
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("old", "root")
    )
    await repo.mark_unknown(KEY, operation_id="old")
    assert (await repo.pending(KEY)).status == "unknown"
    with pytest.raises(SessionExpired):
        await repo.abandon(KEY, "old", expected_session_id="wrong")
    await repo.abandon(KEY, "old", expected_session_id=prepared.session_id)
    await repo.abandon(KEY, "old", expected_session_id=prepared.session_id)
    await enter(repo, op="new")
    assert (await repo.lookup_operation(KEY, operation_id="old")).status == "failed"


async def test_expiry_does_not_extend_and_new_session_invalidates_old_controls():
    repo = repository(session_seconds=1)
    prepared, result = await enter(repo)
    token = NavigationToken(
        "control",
        KEY,
        2,
        prepared.session_id,
        prepared.view_id,
        NavigationAction(target="other"),
        result.snapshot.expires_at,
    )
    await repo.reserve_token(KEY, token, operation_id="token")
    repo.clock.advance(1000)
    assert await repo.load(KEY) is None
    assert await repo.resolve_token(KEY, "control") is None
    new, _ = await enter(repo, op="new-session")
    assert new.session_id != prepared.session_id
    with pytest.raises(SessionExpired):
        await repo.commit(
            KEY,
            expected_version=None,
            mutation=NavigationMutation("old-touch", prepared.session_id, kind="touch"),
        )


async def test_touch_preserves_location_and_background_render_preserves_activity_clock():
    repo = repository()
    _, result = await enter(repo)
    repo.clock.advance(10)
    touch = NavigationMutation("touch", result.snapshot.session_id, kind="touch")
    touched = await repo.commit(KEY, expected_version=result.version, mutation=touch)
    assert touched.snapshot.nav_revision == result.snapshot.nav_revision
    assert touched.snapshot.activity_revision == 2
    assert touched.snapshot.expires_at == result.snapshot.expires_at
    await repo.commit(KEY, expected_version="old", mutation=touch)
    with pytest.raises(OperationIdConflict):
        await repo.commit(KEY, expected_version=None, mutation=replace(touch, source="different"))
    _, background = await enter(repo, op="background", accepted=False, history="none")
    assert background.snapshot.activity_revision == 2
    assert background.snapshot.last_activity_at == touched.snapshot.last_activity_at


async def test_tokens_bind_actor_session_view_and_consumption():
    repo = repository()
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "root")
    )
    token = NavigationToken(
        "control",
        KEY,
        2,
        prepared.session_id,
        prepared.view_id,
        NavigationAction(target="other"),
        prepared.expires_at,
    )
    await repo.reserve_token(KEY, token, operation_id="reserve")
    assert await repo.resolve_token(KEY, "control") is None
    recovered = await repo.reserve_token(
        KEY, replace(token, token="random-retry"), operation_id="reserve"
    )
    assert recovered.token == "control"
    with pytest.raises(OperationIdConflict):
        await repo.reserve_token(
            KEY, replace(token, action=NavigationAction(target="wrong")), operation_id="reserve"
        )
    await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("render", prepared.session_id, RenderResult(prepared.view_id)),
    )
    assert await repo.resolve_token(KEY, "control") == token
    with pytest.raises(StaleView):
        await repo.consume_token(KEY, "control", actor_id=3, operation_id="answer")
    assert await repo.consume_token(KEY, "control", actor_id=2, operation_id="answer") == token
    assert await repo.consume_token(KEY, "control", actor_id=2, operation_id="answer") == token
    with pytest.raises(StaleView):
        await repo.consume_token(KEY, "control", actor_id=2, operation_id="different-answer")
    await enter(repo, op="next")
    assert await repo.resolve_token(KEY, "control") is None


async def test_capacity_retention_and_history_are_bounded_without_evicting_pending():
    repo = repository(
        max_conversations=1,
        max_receipts=2,
        max_tokens=1,
        history_limit=1,
        session_seconds=1,
        recovery_seconds=1,
    )
    first, _ = await enter(repo)
    second, result = await enter(repo, "second", "second")
    assert len(result.snapshot.history) == 1
    with pytest.raises(Overloaded):
        await enter(repo, "third", "third")
    token = NavigationToken(
        "one",
        KEY,
        2,
        second.session_id,
        second.view_id,
        NavigationAction(target="other"),
        second.expires_at,
    )
    await repo.reserve_token(KEY, token, operation_id="token1")
    with pytest.raises(Overloaded):
        await repo.reserve_token(KEY, replace(token, token="two"), operation_id="token2")
    other = ConversationKey("other", 1, 2, 2)
    with pytest.raises(Overloaded):
        await repo.prepare(other, expected_version=None, intent=NavigationIntent("enter", "root"))
    repo.clock.advance(1001)
    assert await repo.sweep(limit=1) == 1
    assert (await repo.lookup_operation(KEY, operation_id="enter")).status == "not_found"
    pending = await repo.prepare(
        other, expected_version=None, intent=NavigationIntent("enter", "root")
    )
    repo.clock.advance(5000)
    assert await repo.sweep(limit=1) == 0
    assert (await repo.pending(other)).session_id == pending.session_id
    await repo.close()


async def test_parallel_prepare_has_one_semantic_winner():
    repo = repository()
    results = await asyncio.gather(
        *(
            repo.prepare(KEY, expected_version=None, intent=NavigationIntent(str(index), "root"))
            for index in range(5)
        ),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(isinstance(result, PendingAction) for result in results) == 4


async def test_task_scopes_are_bound_and_cannot_outlive_parent_or_rebind_storage():
    repo = repository()
    coordinator = MemoryCoordinator()
    repo.bind_coordinator(coordinator)
    other = ConversationKey("other", 1, 2, 2)
    async with coordinator.hold(KEY):
        scope = coordinator.scope_token(KEY)
        with pytest.raises(OwnershipLost):
            await repo.prepare(
                other,
                expected_version=None,
                intent=NavigationIntent("bad", "root"),
                coordination_scope=scope,
            )
        prepared = await repo.prepare(
            KEY,
            expected_version=None,
            intent=NavigationIntent("one", "root"),
            coordination_scope=scope,
        )

        async def child():
            assert coordinator.scope_token(KEY) is None
            await repo.checkpoint(
                KEY,
                operation_id="one",
                effect=EffectCheckpoint("stage", "started"),
                coordination_scope=scope,
            )

        await asyncio.create_task(child())
    with pytest.raises(OwnershipLost):
        await repo.checkpoint(
            KEY,
            operation_id="one",
            effect=EffectCheckpoint("stage", "confirmed", True),
            coordination_scope=scope,
        )
    with pytest.raises(ConfigurationError):
        repo.bind_coordinator(MemoryCoordinator())
    assert prepared.session_id


async def test_expired_request_can_record_receipt_but_cannot_start_or_complete():
    repo = repository(session_seconds=1)
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "root")
    )
    await repo.checkpoint(KEY, operation_id="render", effect=EffectCheckpoint("send", "started"))
    repo.clock.advance(1001)
    await repo.checkpoint(
        KEY, operation_id="render", effect=EffectCheckpoint("send", "confirmed", {"message_id": 5})
    )
    assert (await repo.lookup_operation(KEY, operation_id="render")).prepared.effects[
        "send"
    ].state == "confirmed"
    with pytest.raises(SessionExpired):
        await repo.checkpoint(
            KEY, operation_id="render", effect=EffectCheckpoint("next", "started")
        )
    with pytest.raises(SessionExpired):
        await repo.commit(
            KEY,
            expected_version=None,
            mutation=NavigationMutation(
                "render", prepared.session_id, RenderResult(prepared.view_id)
            ),
        )
    assert await repo.load(KEY) is None


async def test_partial_or_foreign_chat_view_cannot_be_adopted():
    from aiogram_nav.models import MessageRef, ViewState

    repo = repository()
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "root")
    )
    for rendered, error in [
        (ViewState(prepared.view_id, render_status="partial"), RenderUnknown),
        (RenderResult(prepared.view_id, (MessageRef(3, 1),)), StaleView),
    ]:
        with pytest.raises(error):
            await repo.commit(
                KEY,
                expected_version=None,
                mutation=NavigationMutation("render", prepared.session_id, rendered),
            )
    assert await repo.load(KEY) is None
