"""Generic atomic component ownership without importing navigation contracts."""

from dataclasses import replace
from uuid import uuid4

import pytest

from aiogram_idle.clock import ManualClock
from aiogram_idle.config import IdleConfig
from aiogram_idle.errors import ActivityConflict, OwnershipLost, VersionConflict
from aiogram_idle.models import (
    ActionReceipt,
    ActivitySnapshot,
    IdleConversationKey,
    IdleSnapshot,
    Phase,
    RuntimeSnapshot,
    SessionSnapshot,
)
from aiogram_idle.policies import PromptPolicy
from aiogram_idle.receipts import decode_result, encode_result
from aiogram_idle.storage.codec import decode, encode
from aiogram_idle.storage.memory import MemoryIdleBackend

KEY = IdleConversationKey("component-tests", 1, 42, 42)


@pytest.fixture(params=["memory", "redis"])
async def backend(request):
    if request.param == "memory":
        value = MemoryIdleBackend(clock=ManualClock(), config=IdleConfig(enabled=True))
    else:
        url = request.getfixturevalue("redis_url")
        pytest.importorskip("redis.asyncio")
        from redis.asyncio import Redis

        from aiogram_idle.storage.redis import RedisIdleBackend

        client = Redis.from_url(url)
        value = RedisIdleBackend(
            redis=client, prefix=f"component:{uuid4().hex}", config=IdleConfig(enabled=True)
        )
        await value.initialize()
    yield value
    await value.close()
    if request.param == "redis":
        await client.aclose()


def first(backend, *, pending=False):
    now = backend.clock.now()
    session = SessionSnapshot("shared-session", now + 1000)
    activity = ActivitySnapshot(
        "shared-session",
        "activity-one",
        "opaque",
        1,
        "draft",
        "adapter",
        {},
        now,
        now,
        session.expires_at,
    )
    return RuntimeSnapshot(
        KEY,
        session,
        activity,
        IdleSnapshot(phase=Phase.ACTIVE, deadline=now + 10),
        components={
            "opaque": {"ledger": "v1"},
            "__idle_owner__": {
                "component": "opaque",
                "pending": pending,
                "recovery_at": now + 2,
                "retain_until": now + 1000,
            },
            "unrelated": {"value": 1},
        },
    )


async def commit(backend, record, *, version=None, operation="project", scope=None):
    return await backend.component_transaction(
        KEY,
        component="opaque",
        expected_version=version,
        operation_id=operation,
        fingerprint=operation,
        record=record,
        policy=PromptPolicy(10, 20),
        coordination_scope=scope,
    )


async def test_component_activity_and_deadline_commit_together(backend):
    record = first(backend)
    result = await commit(backend, record)
    loaded = await backend.load(KEY)
    assert loaded == result and loaded.components["opaque"]["ledger"] == "v1"
    assert loaded.activity.activity_id == "activity-one"
    # The component's ordinary inactivity deadline was committed in the same save.
    if isinstance(backend.clock, ManualClock):
        backend.clock.advance(11)
        assert len(await backend.claim_due(limit=1, lease_seconds=30)) == 1
    duplicate = await commit(backend, record)
    assert duplicate == result
    with pytest.raises(VersionConflict):
        await commit(backend, record, operation="stale")
    with pytest.raises(ActivityConflict):
        await backend.touch(KEY, expected=loaded.activity.guard, operation_id="standalone")
    with pytest.raises(ActivityConflict):
        await backend.clear(
            KEY, expected=loaded.activity.guard, operation_id="clear", reason="test"
        )
    with pytest.raises(ActivityConflict):
        await backend.enter(
            KEY,
            "other",
            policy_id="draft",
            policy=PromptPolicy(10, 20),
            adapter_key="adapter",
            params={},
            session_id=loaded.session.session_id,
            expires_at=loaded.session.expires_at,
            operation_id="enter",
            expected=loaded.activity.guard,
        )


async def test_component_cannot_alter_other_slots_or_extend_authentication(backend):
    current = await commit(backend, first(backend))
    changed = replace(current, components={**current.components, "unrelated": {"value": 2}})
    with pytest.raises(ActivityConflict):
        await commit(backend, changed, version=current.version, operation="foreign")
    changed = replace(
        current, session=replace(current.session, expires_at=current.session.expires_at + 10)
    )
    with pytest.raises(ActivityConflict):
        await commit(backend, changed, version=current.version, operation="extend")
    async with backend.coordinator.hold(KEY):
        stale_scope = backend.coordinator.scope_token(KEY)
    with pytest.raises(OwnershipLost):
        await commit(
            backend, current, version=current.version, operation="stale-scope", scope=stale_scope
        )


async def test_pending_component_recovery_retained_and_scheduled():
    backend = MemoryIdleBackend(
        clock=ManualClock(), config=IdleConfig(recovery_retention_seconds=1)
    )
    desired = first(backend, pending=True)
    desired = replace(desired, idle=IdleSnapshot())
    record = await commit(backend, desired)
    backend.clock.advance(3)
    claims = await backend.claim_due(limit=1, lease_seconds=1)
    assert len(claims) == 1
    backend.clock.advance(2000)
    await backend.reconcile()
    assert await backend.load(KEY) is not None
    assert (await backend.load(KEY)).activity == record.activity
    latest = await backend.load(KEY)
    marker = dict(latest.components["__idle_owner__"])
    marker["parked"] = True
    parked = replace(latest, components={**latest.components, "__idle_owner__": marker})
    await commit(backend, parked, version=latest.version, operation="park")
    backend.clock.advance(10)
    assert await backend.claim_due(limit=1, lease_seconds=1) == []
    assert await backend.load(KEY) is not None


def test_legacy_action_receipts_decode_and_new_components_roundtrip():
    import json

    legacy = json.loads(encode(ActionReceipt()))
    legacy["value"]["value"].pop("component_updates")
    assert decode(json.dumps(legacy)) == ActionReceipt()
    receipt = ActionReceipt(component_updates={"opaque": {"body": "x" * 20_000}})
    assert decode(encode(receipt)) == receipt
    assert decode_result(encode_result(receipt)) == receipt
    assert decode_result(encode_result("x" * 20_000)) == "x" * 20_000


async def test_staged_component_preserves_captured_worker_claim(backend):
    from aiogram_idle.models import PendingOperation

    desired = first(backend)
    desired = replace(desired, idle=replace(desired.idle, deadline=backend.clock.now() - 1))
    await commit(backend, desired)
    claim = (await backend.claim_due(limit=1, lease_seconds=30))[0]
    async with backend.coordinator.hold(KEY):
        scope = backend.coordinator.scope_token(KEY)
        current = await backend.load(KEY)
        reserved = replace(
            current,
            idle=replace(
                current.idle,
                phase=Phase.RESTORING,
                operation=PendingOperation("worker-op", "restored", started_at=backend.clock.now()),
            ),
        )
        current = await backend.transition(
            KEY,
            expected_version=current.version,
            operation_id="reserve-worker",
            fingerprint="reserve-worker",
            transform=lambda _: reserved,
            claim=claim,
            coordination_scope=scope,
        )
        projected = replace(
            current, components={**current.components, "opaque": {"ledger": "staged"}}
        )
        updated = await backend.component_transaction(
            KEY,
            component="opaque",
            expected_version=current.version,
            operation_id="staged-worker",
            fingerprint="staged-worker",
            record=projected,
            allow_idle_operation_id="worker-op",
            coordination_scope=scope,
            claim=claim,
        )
        assert updated.components["opaque"]["ledger"] == "staged"
        await backend.validate_claim(claim)
        # A matching operation ID alone is not a conversation capability.
        with pytest.raises(OwnershipLost):
            await backend.component_transaction(
                KEY,
                component="opaque",
                expected_version=updated.version,
                operation_id="unowned-worker",
                fingerprint="unowned-worker",
                record=updated,
                allow_idle_operation_id="worker-op",
                claim=claim,
            )
