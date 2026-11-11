from __future__ import annotations

from dataclasses import replace

import pytest

from aiogram_idle.clock import ManualClock
from aiogram_idle.config import IdleConfig
from aiogram_idle.errors import ConfigurationError, ConfigurationMismatch, Overloaded, OwnershipLost
from aiogram_idle.models import IdleConversationKey, IdleSnapshot, Phase
from aiogram_idle.policies import PromptPolicy
from aiogram_idle.storage.memory import MemoryIdleBackend

KEY = IdleConversationKey(namespace="test", bot_id=1, chat_id=2, user_id=2)


async def enter(backend):
    session = await backend.open_session(KEY, lifetime_seconds=1000, operation_id="open")
    return await backend.enter(
        KEY,
        "form",
        policy_id="draft",
        policy=PromptPolicy(10, 20),
        adapter_key="form",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
        enabled=True,
    )


@pytest.mark.parametrize("lifetime", [True, False, float("nan"), float("inf"), -1, 0])
async def test_lifetime_validation(lifetime):
    backend = MemoryIdleBackend()
    with pytest.raises(ValueError):
        await backend.open_session(KEY, lifetime_seconds=lifetime, operation_id="invalid")


async def test_invalid_parameters_fail_before_mutation():
    backend = MemoryIdleBackend(config=IdleConfig(max_params_bytes=32))
    activity = await enter(backend)
    record = await backend.load(KEY)
    for params in ({"large": "x" * 40}, {"number": float("nan")}, {"object": object()}):
        with pytest.raises(ConfigurationError):
            await backend.enter(
                KEY,
                "form",
                policy_id="draft",
                policy=PromptPolicy(),
                adapter_key="form",
                params=params,
                session_id=activity.session_id,
                expires_at=activity.expires_at,
                operation_id="bad",
                expected=activity.guard,
            )
        assert await backend.load(KEY) == record


async def test_atomic_manifest_admission_and_duplicate_after_change():
    backend = MemoryIdleBackend()
    manifest = await backend.bootstrap_config(enabled=True, policies_digest="one")
    activity = await enter(backend)
    touched = await backend.touch(
        KEY,
        expected=activity.guard,
        operation_id="touch",
        enabled=True,
        expected_manifest=manifest.generation,
    )
    await backend.apply_config(
        expected_generation=manifest.generation,
        enabled=False,
        policies_digest="one",
        operation_id="disable",
    )
    assert (
        await backend.touch(
            KEY,
            expected=activity.guard,
            operation_id="touch",
            enabled=True,
            expected_manifest=manifest.generation,
        )
        == touched
    )
    with pytest.raises(ConfigurationMismatch):
        await backend.touch(
            KEY,
            expected=touched.guard,
            operation_id="new",
            enabled=True,
            expected_manifest=manifest.generation,
        )
    assert (await backend.load(KEY)).idle.phase == Phase.DISARMED


async def test_claim_cannot_authorize_other_conversation():
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock)
    await enter(backend)
    other = replace(KEY, namespace="other")
    await backend.open_session(other, lifetime_seconds=100, operation_id="open")
    clock.advance(10)
    claim = (await backend.claim_due(limit=1, lease_seconds=60))[0]
    record = await backend.load(other)
    with pytest.raises(OwnershipLost):
        await backend.transition(
            other,
            expected_version=record.version,
            operation_id="bad",
            fingerprint="fixed",
            transform=lambda value: value,
            claim=claim,
        )


async def test_capacity_does_not_evict_retained_unknown_operation():
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(max_conversations=1))
    await enter(backend)
    record = await backend.load(KEY)
    await backend.transition(
        KEY,
        expected_version=record.version,
        operation_id="unknown",
        fingerprint="fixed",
        transform=lambda value: replace(value, idle=IdleSnapshot(phase=Phase.DELIVERY_UNKNOWN)),
    )
    clock.advance(1001)
    with pytest.raises(Overloaded):
        await backend.open_session(
            replace(KEY, namespace="new"), lifetime_seconds=100, operation_id="new"
        )
    assert (await backend.load(KEY)).idle.phase == Phase.DELIVERY_UNKNOWN
    assert replace(KEY, namespace="new") not in backend._receipts.items


async def test_worker_duplicate_receipt_does_not_authorize_expired_claim():
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock)
    await enter(backend)
    clock.advance(10)
    claim = (await backend.claim_due(limit=1, lease_seconds=5))[0]
    record = await backend.load(KEY)
    await backend.transition(
        KEY,
        expected_version=record.version,
        operation_id="worker:stage",
        fingerprint="fixed",
        transform=lambda value: value,
        claim=claim,
    )
    clock.advance(5)
    newer = (await backend.claim_due(limit=1, lease_seconds=5))[0]
    with pytest.raises(OwnershipLost):
        await backend.transition(
            KEY,
            expected_version=record.version,
            operation_id="worker:stage",
            fingerprint="fixed",
            transform=lambda value: value,
            claim=claim,
        )
    await backend.validate_claim(newer)
