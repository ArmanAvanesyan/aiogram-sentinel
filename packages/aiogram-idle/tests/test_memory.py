from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from aiogram_idle.clock import ManualClock
from aiogram_idle.config import IdleConfig
from aiogram_idle.errors import (
    ActivityConflict,
    ConfigurationMismatch,
    OperationIdConflict,
    Overloaded,
    OwnershipLost,
    SessionExpired,
    VersionConflict,
)
from aiogram_idle.models import IdleConversationKey, IdleSnapshot, Phase, freeze_object
from aiogram_idle.policies import ExemptPolicy, PromptPolicy
from aiogram_idle.storage.memory import MemoryIdleBackend


@pytest.fixture
def key() -> IdleConversationKey:
    return IdleConversationKey(namespace="test", bot_id=123, chat_id=42, user_id=42)


async def setup_activity(backend: MemoryIdleBackend, key: IdleConversationKey):
    session = await backend.open_session(key, lifetime_seconds=1000, operation_id="open")
    activity = await backend.enter(
        key,
        "form",
        policy_id="draft",
        policy=PromptPolicy(10, 20),
        adapter_key="form",
        params={"nested": [1]},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
        enabled=True,
    )
    return session, activity


async def test_session_and_mutation_dedup_precedes_guard(key):
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock)
    session, activity = await setup_activity(backend, key)
    assert await backend.open_session(key, lifetime_seconds=1000, operation_id="open") == session
    touched = await backend.touch(key, expected=activity.guard, operation_id="touch", enabled=True)
    assert touched.activity_revision == 2
    assert (
        await backend.touch(key, expected=activity.guard, operation_id="touch", enabled=True)
        == touched
    )
    with pytest.raises(ActivityConflict):
        await backend.touch(key, expected=activity.guard, operation_id="other", enabled=True)
    with pytest.raises(OperationIdConflict):
        await backend.touch(key, expected=touched.guard, operation_id="touch", enabled=True)
    await backend.clear(key, expected=touched.guard, reason="cancel", operation_id="clear")
    await backend.clear(key, expected=touched.guard, reason="cancel", operation_id="clear")
    assert (await backend.load(key)).activity is None


async def test_aba_and_session_replacement(key):
    backend = MemoryIdleBackend()
    session, old = await setup_activity(backend, key)
    new = await backend.enter(
        key,
        "form",
        policy_id="draft",
        policy=PromptPolicy(10, 20),
        adapter_key="form",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="reenter",
        expected=old.guard,
    )
    assert new.activity_id != old.activity_id
    with pytest.raises(ActivityConflict):
        await backend.clear(key, expected=old.guard, operation_id="old", reason="cancel")
    replacement = await backend.replace_session(
        key, expected=session.guard, lifetime_seconds=100, operation_id="replace"
    )
    assert replacement.session_id != session.session_id
    assert (
        await backend.replace_session(
            key, expected=session.guard, lifetime_seconds=100, operation_id="replace"
        )
        == replacement
    )
    with pytest.raises(ActivityConflict):
        await backend.replace_session(
            key, expected=session.guard, lifetime_seconds=100, operation_id="stale-replace"
        )


async def test_no_implicit_replacement_or_expiry_extension(key):
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock)
    session, activity = await setup_activity(backend, key)
    with pytest.raises(ActivityConflict):
        await backend.open_session(key, lifetime_seconds=1, operation_id="open2")
    with pytest.raises(ActivityConflict):
        await backend.enter(
            key,
            "other",
            policy_id="draft",
            policy=PromptPolicy(),
            adapter_key="form",
            params={},
            session_id=session.session_id,
            expires_at=session.expires_at,
            operation_id="enter2",
        )
    clock.advance(10)
    touched = await backend.touch(key, expected=activity.guard, operation_id="touch")
    assert touched.expires_at == session.expires_at
    clock.advance(991)
    with pytest.raises(SessionExpired):
        await backend.touch(key, expected=touched.guard, operation_id="expired")


async def test_input_detached_and_invalid_inputs_atomic(key):
    backend = MemoryIdleBackend()
    session = await backend.open_session(key, lifetime_seconds=100, operation_id="open")
    params = {"nested": [1]}
    activity = await backend.enter(
        key,
        "form",
        policy_id="draft",
        policy=ExemptPolicy(),
        adapter_key="form",
        params=params,
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
    )
    params["nested"].append(2)
    assert activity.params["nested"] == (1,)
    with pytest.raises(TypeError):
        activity.params["secret"] = "changed"
    with pytest.raises(ValueError):
        await backend.enter(
            key,
            "bad",
            policy_id="draft",
            policy=ExemptPolicy(),
            adapter_key="form",
            params={},
            session_id=session.session_id,
            expires_at=session.expires_at + 1,
            operation_id="invalid",
            expected=activity.guard,
        )
    assert (await backend.load(key)).activity == activity
    with pytest.raises(ValueError):
        await backend.open_session(key, lifetime_seconds=float("inf"), operation_id="infinite")


async def test_due_claim_reclaim_and_old_token_fencing(key):
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock)
    await setup_activity(backend, key)
    assert await backend.claim_due(limit=1, lease_seconds=5) == []
    clock.advance(10)
    first = (await backend.claim_due(limit=1, lease_seconds=5))[0]
    assert await backend.claim_due(limit=1, lease_seconds=5) == []
    clock.advance(5)
    with pytest.raises(OwnershipLost):
        await backend.renew_claim(first, lease_seconds=5)
    second = (await backend.claim_due(limit=1, lease_seconds=5))[0]
    assert first.token != second.token
    with pytest.raises(OwnershipLost):
        await backend.release_claim(first)
    await backend.validate_claim(second)
    await backend.release_claim(second, retry_at=clock.now() + 10)
    assert await backend.claim_due(limit=1, lease_seconds=5) == []


async def test_atomic_claims_and_renewal(key):
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock)
    await setup_activity(backend, key)
    clock.advance(10)
    results = await asyncio.gather(*(backend.claim_due(limit=1, lease_seconds=5) for _ in range(8)))
    claims = [claim for group in results for claim in group]
    assert len(claims) == 1
    clock.advance(4)
    renewed = await backend.renew_claim(claims[0], lease_seconds=5)
    assert renewed.lease_until == clock.now() + 5
    clock.advance(2)
    assert await backend.claim_due(limit=1, lease_seconds=5) == []


async def test_activity_invalidates_old_worker_and_heap_compacts(key):
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(max_receipts_per_conversation=1000))
    _, activity = await setup_activity(backend, key)
    clock.advance(10)
    claim = (await backend.claim_due(limit=1, lease_seconds=60))[0]
    record = await backend.load(key)
    for n in range(200):
        activity = await backend.touch(
            key, expected=activity.guard, operation_id=f"touch:{n}", enabled=True
        )
    with pytest.raises(OwnershipLost):
        await backend.transition(
            key,
            expected_version=record.version,
            operation_id="old-worker",
            fingerprint="fixed",
            transform=lambda value: value,
            claim=claim,
        )
    assert len(backend._queue.heap) <= 2 * len(backend._queue.jobs) + 128
    assert await backend.claim_due(limit=1, lease_seconds=60) == []


async def test_transition_checkpoint_dedup_and_version_fence(key):
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock)
    await setup_activity(backend, key)
    clock.advance(10)
    claim = (await backend.claim_due(limit=1, lease_seconds=60))[0]
    record = await backend.load(key)

    def transform(value):
        return replace(
            value, idle=IdleSnapshot(phase=Phase.PROMPT_PENDING, deadline=clock.now() + 5)
        )

    updated = await backend.transition(
        key,
        expected_version=record.version,
        operation_id="reserve",
        fingerprint="same",
        transform=transform,
        claim=claim,
    )
    assert updated.version == record.version + 1
    assert (
        await backend.transition(
            key,
            expected_version=record.version,
            operation_id="reserve",
            fingerprint="same",
            transform=transform,
            claim=claim,
        )
        == updated
    )
    await backend.validate_claim(claim)
    with pytest.raises(VersionConflict):
        await backend.transition(
            key,
            expected_version=record.version,
            operation_id="bad-version",
            fingerprint="different",
            transform=transform,
            claim=claim,
        )
    with pytest.raises(ActivityConflict):
        await backend.transition(
            key,
            expected_version=updated.version,
            operation_id="bad-key",
            fingerprint="bad",
            transform=lambda value: replace(value, key=replace(key, namespace="other")),
        )


async def test_receipts_conversation_and_token_limits(key):
    clock = ManualClock()
    backend = MemoryIdleBackend(
        clock=clock,
        config=IdleConfig(
            max_conversations=1, max_receipts_per_conversation=2, max_tokens_per_conversation=1
        ),
    )
    _, activity = await setup_activity(backend, key)
    with pytest.raises(Overloaded):
        await backend.touch(key, expected=activity.guard, operation_id="third")
    assert (await backend.load(key)).activity == activity
    with pytest.raises(Overloaded):
        await backend.open_session(
            replace(key, namespace="other"), lifetime_seconds=100, operation_id="new"
        )
    token = await backend.reserve_control(
        key,
        token="one",
        prompt_id="prompt",
        activity_id=activity.activity_id,
        expires_at=clock.now() + 100,
    )
    assert await backend.resolve_control(key, "one") == token
    with pytest.raises(Overloaded):
        await backend.reserve_control(
            key,
            token="two",
            prompt_id="prompt",
            activity_id=activity.activity_id,
            expires_at=clock.now() + 100,
        )
    assert await backend.resolve_control(replace(key, namespace="other"), "one") is None
    clock.advance(101)
    assert await backend.resolve_control(key, "one") is None


async def test_config_cas_disable_does_not_rearm_on_enable(key):
    backend = MemoryIdleBackend()
    config = await backend.bootstrap_config(enabled=True, policies_digest="digest")
    assert await backend.bootstrap_config(enabled=True, policies_digest="digest") == config
    with pytest.raises(ConfigurationMismatch):
        await backend.bootstrap_config(enabled=False, policies_digest="digest")
    await setup_activity(backend, key)
    disabled = await backend.apply_config(
        expected_generation=config.generation,
        enabled=False,
        policies_digest="digest",
        operation_id="disable",
    )
    assert (await backend.load(key)).idle.phase == Phase.DISARMED
    assert (
        await backend.apply_config(
            expected_generation=config.generation,
            enabled=False,
            policies_digest="digest",
            operation_id="disable",
        )
        == disabled
    )
    with pytest.raises(OperationIdConflict):
        await backend.apply_config(
            expected_generation=config.generation,
            enabled=True,
            policies_digest="digest",
            operation_id="disable",
        )
    await backend.apply_config(
        expected_generation=disabled.generation,
        enabled=True,
        policies_digest="digest",
        operation_id="enable",
    )
    assert (await backend.load(key)).idle.deadline is None


async def test_reconcile_missing_due_and_prune_expired(key):
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(recovery_retention_seconds=10))
    await setup_activity(backend, key)
    backend._queue.jobs.clear()
    assert await backend.reconcile(limit=1) == 1
    assert key in backend._queue.jobs
    clock.advance(1001)
    await backend.reconcile(limit=1)
    assert await backend.load(key) is None


async def test_components_preserved_and_frozen_policy(key):
    backend = MemoryIdleBackend()
    _, activity = await setup_activity(backend, key)
    record = await backend.load(key)
    await backend.transition(
        key,
        expected_version=record.version,
        operation_id="components",
        fingerprint="fixed",
        transform=lambda value: replace(value, components=freeze_object({"custom": {"value": 1}})),
    )
    await backend.clear(key, expected=activity.guard, operation_id="clear", reason="done")
    assert (await backend.load(key)).components["custom"] == {"value": 1}
    assert await backend.frozen_policy(key) == PromptPolicy(10, 20)
    await backend.close()
