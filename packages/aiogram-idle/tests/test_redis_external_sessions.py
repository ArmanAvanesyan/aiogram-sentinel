"""Real Redis preserves read-only authority bindings across replica recovery."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from aiogram_coordination import ExternalSession

from aiogram_idle import (
    ActivityRegistration,
    IdleConfig,
    IdlePolicies,
    IdleRuntime,
    Phase,
    PromptPolicy,
)
from aiogram_idle.storage.redis import RedisIdleBackend
from aiogram_idle.storage.session_bindings import EXTERNAL_SESSION
from tests.runtime_helpers import Adapter, Presenter
from tests.test_external_sessions import KEY, Authority


async def runtime_for(backend, authority):
    await backend.initialize()
    adapter = Adapter()
    presenter = Presenter(backend.clock)
    runtime = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"prompt": PromptPolicy(0.01, 10)}),
        adapters={"form": adapter},
        presenter=presenter,
        namespace="test",
        session_authority=authority,
    )
    await runtime.initialize()
    return runtime, adapter, presenter


async def build(client):
    backend = RedisIdleBackend(
        redis=client,
        prefix="external:" + uuid4().hex,
        config=IdleConfig(enabled=True, poll_seconds=0.01),
    )
    await backend.initialize()
    authority = Authority()
    now = int(backend.clock.now() * 1000)
    authority.value = ExternalSession("application", "1", now + 3600000, now + 1800000)
    runtime, adapter, presenter = await runtime_for(backend, authority)
    if await backend.storage_format() < 2:
        await backend.activate_storage_format(
            operation_id="activate", old_workers_drained=True, dry_run=False
        )
    activity = await runtime.for_conversation(KEY).activate(
        ActivityRegistration("form", "prompt", "form", {"draft_id": "draft"}), operation_id="enter"
    )
    return runtime, backend, authority, adapter, presenter, activity


async def test_external_binding_round_trips_and_fences_old_generation(redis_client):
    runtime, backend, authority, _, _, activity = await build(redis_client)
    record = await backend.load(KEY)
    assert record.session.session_id == activity.session_id
    assert record.components[EXTERNAL_SESSION]["session_id"] == "application"
    replica = RedisIdleBackend(
        redis=redis_client, prefix=backend._store.prefix, config=backend.config
    )
    second, _, _ = await runtime_for(replica, authority)
    assert (await second.inspect(KEY)).session == record.session
    assert await replica.storage_format() == await backend.storage_format()
    assert await replica.storage_format() >= 2
    authority.value = replace(authority.value, session_id="replacement")
    from aiogram_idle import SessionExpired

    with pytest.raises(SessionExpired):
        await second.for_conversation(KEY).touch(
            expected=activity.guard, operation_id="stale-touch"
        )
    assert (await backend.load(KEY)).activity.guard == activity.guard


async def test_crashed_external_claim_recovers_on_another_replica(redis_client):
    runtime, backend, authority, _, presenter, _ = await build(redis_client)
    await asyncio.sleep(0.03)
    claims = await backend.claim_due(limit=1, lease_seconds=0.04)
    assert len(claims) == 1
    replica = RedisIdleBackend(
        redis=redis_client, prefix=backend._store.prefix, config=backend.config
    )
    second, _, other = await runtime_for(replica, authority)
    assert not (await second.run_once()).claimed
    await asyncio.sleep(0.06)
    result = await second.run_once()
    assert result.completed == 1
    assert len(other.questions) == 1 and presenter.questions == []
    assert (await backend.load(KEY)).idle.phase is Phase.PROMPTED


async def test_external_authority_outage_leaves_redis_activity_intact(redis_client):
    runtime, backend, authority, adapter, presenter, activity = await build(redis_client)
    authority.error = TimeoutError("unavailable")
    await asyncio.sleep(0.03)
    assert not (await runtime.run_once()).completed
    record = await backend.load(KEY)
    assert record.activity.guard == activity.guard and record.idle.phase is Phase.ACTIVE
    assert not adapter.calls and not presenter.questions
    authority.error = None
    assert (await runtime.run_once()).completed == 1
    assert len(presenter.questions) == 1
