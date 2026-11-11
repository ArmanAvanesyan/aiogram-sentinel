from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from aiogram_idle import (
    IdleConfig,
    IdleConversationKey,
    IdleSnapshot,
    ManualClock,
    MemoryIdleBackend,
    OperationIdConflict,
    Overloaded,
    PendingOperation,
    Phase,
    PromptPolicy,
)

KEY = IdleConversationKey("audit", 1, 2, 2)


async def entered(backend, *, lifetime=100):
    session = await backend.open_session(KEY, lifetime_seconds=lifetime, operation_id="open")
    activity = await backend.enter(
        KEY,
        "draft",
        policy_id="draft",
        policy=PromptPolicy(10, 20),
        adapter_key="draft",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
        enabled=True,
    )
    return session, activity


async def test_enter_fingerprints_the_detached_params_snapshot():
    backend = MemoryIdleBackend(clock=ManualClock())
    session = await backend.open_session(KEY, lifetime_seconds=100, operation_id="open")
    params = {"value": "original"}
    await backend._lock.acquire()
    task = asyncio.create_task(
        backend.enter(
            KEY,
            "draft",
            policy_id="draft",
            policy=PromptPolicy(10, 20),
            adapter_key="draft",
            params=params,
            session_id=session.session_id,
            expires_at=session.expires_at,
            operation_id="enter",
            enabled=True,
        )
    )
    try:
        await asyncio.sleep(0)
        params["value"] = "changed"
    finally:
        backend._lock.release()
    activity = await task
    assert activity.params["value"] == "original"
    with pytest.raises(OperationIdConflict):
        await backend.enter(
            KEY,
            "draft",
            policy_id="draft",
            policy=PromptPolicy(10, 20),
            adapter_key="draft",
            params=params,
            session_id=session.session_id,
            expires_at=session.expires_at,
            operation_id="enter",
            enabled=True,
        )


async def test_expired_admin_receipts_do_not_permanently_exhaust_capacity():
    clock = ManualClock()
    backend = MemoryIdleBackend(
        clock=clock,
        config=IdleConfig(
            max_receipts_per_conversation=1,
            recovery_retention_seconds=1,
        ),
    )
    initial = await backend.bootstrap_config(enabled=False, policies_digest="policies")
    first = await backend.apply_config(
        expected_generation=initial.generation,
        enabled=True,
        policies_digest="policies",
        operation_id="first",
    )
    clock.advance(2)
    second = await backend.apply_config(
        expected_generation=first.generation,
        enabled=False,
        policies_digest="policies",
        operation_id="second",
    )
    assert not second.enabled


@pytest.mark.parametrize(
    "phase", [Phase.PROMPT_PENDING, Phase.RESUMING, Phase.ABANDONING, Phase.RESTORING]
)
async def test_capacity_does_not_evict_unresolved_operation_after_session_expiry(phase):
    clock = ManualClock()
    backend = MemoryIdleBackend(
        clock=clock,
        config=IdleConfig(
            max_conversations=1,
            recovery_retention_seconds=1,
        ),
    )
    await entered(backend, lifetime=2)
    current = await backend.load(KEY)
    await backend.transition(
        KEY,
        expected_version=current.store_version,
        operation_id="reserve",
        fingerprint="reserve",
        transform=lambda record: replace(
            record,
            idle=IdleSnapshot(
                phase=phase,
                deadline=clock.now(),
                operation=PendingOperation(operation_id="pending", kind="prompt"),
            ),
        ),
    )
    clock.advance(3)
    with pytest.raises(Overloaded):
        await backend.open_session(
            IdleConversationKey("audit", 1, 3, 3), lifetime_seconds=100, operation_id="other-open"
        )
    assert await backend.load(KEY) is not None


async def test_reconciliation_preserves_pending_work_past_logical_expiry():
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(recovery_retention_seconds=1))
    await entered(backend, lifetime=2)
    current = await backend.load(KEY)
    await backend.transition(
        KEY,
        expected_version=current.store_version,
        operation_id="reserve",
        fingerprint="reserve",
        transform=lambda record: replace(
            record,
            idle=IdleSnapshot(
                phase=Phase.RESUMING,
                deadline=clock.now(),
                operation=PendingOperation(operation_id="pending", kind="continue"),
            ),
        ),
    )
    clock.advance(3)
    await backend.reconcile()
    assert await backend.load(KEY) is not None


@pytest.mark.parametrize("mutation", ["enter", "touch", "clear", "replace_session", "open_session"])
async def test_public_activity_mutation_cannot_erase_reserved_operation(mutation):
    from aiogram_idle import ActivityConflict

    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock)
    session, activity = await entered(backend, lifetime=2 if mutation == "open_session" else 100)
    current = await backend.load(KEY)
    reserved = await backend.transition(
        KEY,
        expected_version=current.store_version,
        operation_id="reserve",
        fingerprint="reserve",
        transform=lambda record: replace(
            record,
            idle=IdleSnapshot(
                phase=Phase.RESUMING,
                deadline=clock.now(),
                operation=PendingOperation(operation_id="pending", kind="continue"),
            ),
        ),
    )
    if mutation == "open_session":
        clock.advance(3)
    with pytest.raises(ActivityConflict):
        if mutation == "enter":
            await backend.enter(
                KEY,
                "new-draft",
                policy_id="draft",
                policy=PromptPolicy(10, 20),
                adapter_key="draft",
                params={},
                session_id=session.session_id,
                expires_at=session.expires_at,
                operation_id="new-enter",
                expected=activity.guard,
            )
        elif mutation == "touch":
            await backend.touch(KEY, expected=activity.guard, operation_id="new-touch")
        elif mutation == "clear":
            await backend.clear(
                KEY, expected=activity.guard, operation_id="new-clear", reason="manual"
            )
        elif mutation == "replace_session":
            await backend.replace_session(
                KEY, expected=session.guard, operation_id="replace", lifetime_seconds=100
            )
        else:
            await backend.open_session(KEY, lifetime_seconds=100, operation_id="new-open")
    after = await backend.load(KEY)
    assert after == reserved


async def test_backend_coordinator_cannot_be_rebound_during_scope_or_after_records():
    from aiogram_idle import ConfigurationError, MemoryCoordinator

    backend = MemoryIdleBackend()
    initial = backend.coordinator
    proposed = MemoryCoordinator()
    backend.bind_coordinator(initial)
    async with initial.hold(KEY):
        with pytest.raises(ConfigurationError):
            backend.bind_coordinator(proposed)
    backend.bind_coordinator(proposed)
    assert backend.coordinator is proposed
    await backend.open_session(KEY, lifetime_seconds=100, operation_id="open")
    with pytest.raises(ConfigurationError):
        backend.bind_coordinator(initial)
    assert backend.coordinator is proposed


async def test_live_claim_prevents_pruning_even_after_terminal_state_retention():
    clock = ManualClock()
    backend = MemoryIdleBackend(
        clock=clock,
        config=IdleConfig(
            max_conversations=1,
            recovery_retention_seconds=1,
        ),
    )
    await entered(backend, lifetime=2)
    current = await backend.load(KEY)
    await backend.transition(
        KEY,
        expected_version=current.store_version,
        operation_id="due",
        fingerprint="due",
        transform=lambda record: replace(
            record,
            idle=IdleSnapshot(
                phase=Phase.ACTIVE,
                deadline=clock.now(),
            ),
        ),
    )
    (claim,) = await backend.claim_due(limit=1, lease_seconds=60)
    current = await backend.load(KEY)
    await backend.transition(
        KEY,
        expected_version=current.store_version,
        operation_id="finished",
        fingerprint="finished",
        claim=claim,
        transform=lambda record: replace(record, idle=IdleSnapshot()),
    )
    clock.advance(3)
    with pytest.raises(Overloaded):
        await backend.open_session(
            IdleConversationKey("audit", 1, 3, 3), lifetime_seconds=100, operation_id="other-open"
        )
    await backend.release_claim(claim)
    await backend.open_session(
        IdleConversationKey("audit", 1, 3, 3), lifetime_seconds=100, operation_id="other-open"
    )


async def test_claim_filters_preserve_foreign_jobs_without_starving_owned_work():
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock)
    foreign_namespace = replace(KEY, namespace="foreign")
    foreign_bot = replace(KEY, bot_id=3)
    for key in (foreign_namespace, foreign_bot, KEY):
        session = await backend.open_session(key, lifetime_seconds=100, operation_id="open")
        await backend.enter(
            key,
            "draft",
            policy_id="draft",
            policy=PromptPolicy(10, 20),
            adapter_key="draft",
            params={},
            session_id=session.session_id,
            expires_at=session.expires_at,
            operation_id="enter",
            enabled=True,
        )
    clock.advance(11)
    owned = await backend.claim_due(limit=1, lease_seconds=60, namespace="audit", bot_id=1)
    assert [claim.key for claim in owned] == [KEY]
    assert not await backend.claim_due(limit=1, lease_seconds=60, namespace="audit", bot_id=1)
    namespace_claim = await backend.claim_due(limit=1, lease_seconds=60, namespace="foreign")
    assert [claim.key for claim in namespace_claim] == [foreign_namespace]
    bot_claim = await backend.claim_due(limit=1, lease_seconds=60, namespace="audit", bot_id=3)
    assert [claim.key for claim in bot_claim] == [foreign_bot]


async def test_operation_lookup_distinguishes_missing_retained_and_unknown_history():
    clock = ManualClock()
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(recovery_retention_seconds=10))
    born = clock.now()
    missing = await backend.lookup_operation(KEY, "missing")
    assert missing.status == "unknown_history"
    retained = await backend.lookup_operation(KEY, "missing", not_before=born)
    assert retained.status == "not_found_within_retention"
    session = await backend.open_session(KEY, lifetime_seconds=100, operation_id="open")
    found = await backend.lookup_operation(KEY, "open")
    assert found.status == "found" and found.result == session
    clock.advance(10)
    expired = await backend.lookup_operation(KEY, "open", not_before=born)
    assert expired.status == "unknown_history"
    fresh = await backend.lookup_operation(KEY, "missing", not_before=clock.now())
    assert fresh.status == "not_found_within_retention"
    assert (
        await backend.lookup_operation(KEY, "missing", not_before=clock.now() + 1)
    ).status == "unknown_history"
    restarted = MemoryIdleBackend(clock=clock)
    assert (
        await restarted.lookup_operation(KEY, "missing", not_before=born)
    ).status == "unknown_history"
