"""Real backend state mutations use the selected deterministic engine."""

from uuid import uuid4

import pytest

pytest.importorskip("aiogram_idle_native")

from aiogram_idle import (
    ActivityConflict,
    IdleConfig,
    IdleConversationKey,
    MemoryIdleBackend,
    OwnershipLost,
    PromptPolicy,
)
from aiogram_idle.clock import ManualClock
from aiogram_idle.models import ActivityGuard
from aiogram_idle.storage.redis import RedisIdleBackend


@pytest.mark.parametrize("engine", ["python", "rust"])
async def test_memory_backend_claim_crash_recovery_guards_and_receipt_replay(engine):
    clock = ManualClock(100)
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(enabled=True, engine=engine))
    key = IdleConversationKey("native", 1, 42, 42)
    session = await backend.open_session(key, lifetime_seconds=100, operation_id="session")
    activity = await backend.enter(
        key,
        "form",
        policy_id="form",
        policy=PromptPolicy(after_seconds=1),
        adapter_key="form",
        params={"draft": 1},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="entry",
        enabled=True,
    )
    bad = ActivityGuard(activity.session_id, activity.activity_id, activity.activity_revision + 1)
    with pytest.raises(ActivityConflict):
        await backend.touch(key, expected=bad, operation_id="wrong", enabled=True)
    clock.advance(2)
    first = (await backend.claim_due(limit=1, lease_seconds=2))[0]
    clock.advance(2)
    second = (await backend.claim_due(limit=1, lease_seconds=2))[0]
    assert first.token != second.token
    with pytest.raises(OwnershipLost):
        await backend.renew_claim(first, lease_seconds=2)
    await backend.release_claim(second, retry_at=clock.now() + 10)
    touched = await backend.touch(key, expected=activity.guard, operation_id="touch", enabled=True)
    assert (
        await backend.touch(key, expected=activity.guard, operation_id="touch", enabled=True)
        == touched
    )
    assert touched.activity_revision == activity.activity_revision + 1


@pytest.mark.parametrize(
    "writer,reader",
    [("python", "python"), ("python", "rust"), ("rust", "python"), ("rust", "rust")],
)
async def test_redis_cross_engine_receipt_guards_and_live_state(redis_client, writer, reader):
    prefix = "test:native:cross:" + uuid4().hex
    first = RedisIdleBackend(redis=redis_client, prefix=prefix, config=IdleConfig(engine=writer))
    second = RedisIdleBackend(redis=redis_client, prefix=prefix, config=IdleConfig(engine=reader))
    key = IdleConversationKey("native", 1, 42, 42)
    session = await first.open_session(key, lifetime_seconds=100, operation_id="session")
    assert await second.open_session(key, lifetime_seconds=100, operation_id="session") == session
    activity = await first.enter(
        key,
        "form",
        policy_id="form",
        policy=PromptPolicy(),
        adapter_key="form",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="entry",
    )
    touched = await second.touch(key, expected=activity.guard, operation_id="touch")
    assert await first.touch(key, expected=activity.guard, operation_id="touch") == touched
    assert (await first.load(key)).activity == touched
