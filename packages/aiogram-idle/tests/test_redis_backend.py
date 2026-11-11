"""Shared domain contracts exercised against memory and a real Redis server."""

from dataclasses import replace
from uuid import uuid4

import pytest

from aiogram_idle.config import IdleConfig
from aiogram_idle.errors import ActivityConflict, OperationIdConflict, Overloaded, OwnershipLost
from aiogram_idle.models import IdleConversationKey
from aiogram_idle.policies import PromptPolicy
from aiogram_idle.storage.memory import MemoryIdleBackend


@pytest.fixture(params=["memory", "redis"])
async def backend(request, redis_client):
    kind, config = (
        request.param if isinstance(request.param, tuple) else (request.param, IdleConfig())
    )
    if kind == "memory":
        instance = MemoryIdleBackend(config=config)
    else:
        from aiogram_idle.storage.redis import RedisIdleBackend

        instance = RedisIdleBackend(
            redis=redis_client, prefix=f"test:idle:{uuid4().hex}", config=config
        )
        await instance.initialize()
    yield instance
    await instance.close()


async def seed(backend):
    key = IdleConversationKey("test", 1, 42, 42)
    session = await backend.open_session(key, lifetime_seconds=300, operation_id="open")
    activity = await backend.enter(
        key,
        "form",
        policy_id="draft",
        policy=PromptPolicy(10, 20),
        adapter_key="form",
        params={"nested": [1], "draft_id": "draft"},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
        enabled=True,
    )
    return key, session, activity


async def make_due(backend, key):
    record = await backend.load(key)
    assert record is not None
    await backend.transition(
        key,
        expected_version=record.version,
        operation_id=f"due:{uuid4().hex}",
        fingerprint="make-due",
        transform=lambda old: replace(
            old, idle=replace(old.idle, deadline=backend.clock.now() - 1)
        ),
    )


async def test_backend_contract_receipts_guards_and_reentry(backend):
    key, session, activity = await seed(backend)
    assert await backend.open_session(key, lifetime_seconds=300, operation_id="open") == session
    touched = await backend.touch(key, expected=activity.guard, operation_id="touch", enabled=True)
    assert touched.activity_revision == activity.activity_revision + 1
    assert touched.expires_at == activity.expires_at
    assert (
        await backend.touch(key, expected=activity.guard, operation_id="touch", enabled=True)
        == touched
    )
    with pytest.raises(ActivityConflict):
        await backend.touch(key, expected=activity.guard, operation_id="stale", enabled=True)
    with pytest.raises(OperationIdConflict):
        await backend.touch(key, expected=touched.guard, operation_id="touch", enabled=True)
    fresh = await backend.enter(
        key,
        "form",
        policy_id="draft",
        policy=PromptPolicy(10, 20),
        adapter_key="form",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="reenter",
        expected=touched.guard,
        enabled=True,
    )
    assert fresh.activity_id != activity.activity_id
    await backend.clear(key, expected=fresh.guard, operation_id="clear", reason="cancel")
    await backend.clear(key, expected=fresh.guard, operation_id="clear", reason="cancel")
    assert (await backend.load(key)).activity is None
    assert (await backend.lookup_operation(key, "clear")).status == "found"


async def test_backend_contract_manifest_does_not_implicitly_change(backend):
    first = await backend.bootstrap_config(enabled=False, policies_digest="one")
    assert await backend.bootstrap_config(enabled=False, policies_digest="one") == first
    updated = await backend.apply_config(
        expected_generation=first.generation,
        enabled=True,
        policies_digest="two",
        operation_id="enable",
    )
    assert updated.generation != first.generation
    assert await backend.get_config() == updated


async def test_backend_contract_claim_generation_fences_new_activity(backend):
    key, _, activity = await seed(backend)
    await make_due(backend, key)
    claims = await backend.claim_due(limit=1, lease_seconds=5)
    assert len(claims) == 1
    await backend.touch(key, expected=activity.guard, operation_id="new-activity", enabled=True)
    with pytest.raises(OwnershipLost):
        await backend.renew_claim(claims[0], lease_seconds=5)
    with pytest.raises(OwnershipLost):
        await backend.release_claim(claims[0])
    current = await backend.load(key)
    assert current.activity.activity_revision == activity.activity_revision + 1
    await make_due(backend, key)
    assert len(await backend.claim_due(limit=1, lease_seconds=5)) == 1


async def test_backend_contract_tokens_are_generation_bound(backend):
    key, session, activity = await seed(backend)
    token = await backend.reserve_control(
        key,
        token="continue-token",
        prompt_id="prompt-one",
        activity_id=activity.activity_id,
        expires_at=session.expires_at,
    )
    assert await backend.resolve_control(key, "continue-token") == token
    fresh = await backend.enter(
        key,
        "form",
        policy_id="draft",
        policy=PromptPolicy(10, 20),
        adapter_key="form",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="next-generation",
        expected=activity.guard,
        enabled=True,
    )
    assert fresh.activity_id != token.activity_id
    assert await backend.resolve_control(key, "continue-token") is None


async def test_backend_contract_transition_dedup_before_stale_version(backend):
    key, _, _ = await seed(backend)
    before = await backend.load(key)
    first = await backend.transition(
        key,
        expected_version=before.version,
        operation_id="transition",
        fingerprint="same",
        transform=lambda value: replace(value, recovery_until=value.session.expires_at + 60),
    )
    duplicate = await backend.transition(
        key,
        expected_version=before.version,
        operation_id="transition",
        fingerprint="same",
        transform=lambda _: pytest.fail("Duplicate must not rerun transform"),
    )
    assert first == duplicate
    with pytest.raises(OperationIdConflict):
        await backend.transition(
            key,
            expected_version=first.version,
            operation_id="transition",
            fingerprint="different",
            transform=lambda value: value,
        )


async def test_backend_contract_disabled_manifest_disarms_before_reenable(backend):
    manifest = await backend.bootstrap_config(enabled=True, policies_digest="one")
    key, _, _ = await seed(backend)
    disabled = await backend.apply_config(
        expected_generation=manifest.generation,
        enabled=False,
        policies_digest="one",
        operation_id="disable",
    )
    current = await backend.load(key)
    assert current.idle.deadline is None
    await backend.apply_config(
        expected_generation=disabled.generation,
        enabled=True,
        policies_digest="one",
        operation_id="enable-again",
    )
    current = await backend.load(key)
    assert current.idle.deadline is None
    assert await backend.claim_due(limit=10, lease_seconds=5) == []


async def test_backend_contract_namespace_filter_preserves_other_due_jobs(backend):
    key, session, _ = await seed(backend)
    foreign = replace(key, namespace="foreign", bot_id=2)
    other_session = await backend.open_session(
        foreign, lifetime_seconds=300, operation_id="other-open"
    )
    await backend.enter(
        foreign,
        "form",
        policy_id="draft",
        policy=PromptPolicy(10, 20),
        adapter_key="form",
        params={},
        session_id=other_session.session_id,
        expires_at=other_session.expires_at,
        operation_id="other-enter",
        enabled=True,
    )
    assert session.session_id != other_session.session_id
    await make_due(backend, foreign)
    await make_due(backend, key)
    own_claims = await backend.claim_due(limit=1, lease_seconds=5, namespace="test", bot_id=1)
    assert [claim.key for claim in own_claims] == [key]
    foreign_claims = await backend.claim_due(
        limit=1, lease_seconds=5, namespace="foreign", bot_id=2
    )
    assert [claim.key for claim in foreign_claims] == [foreign]


@pytest.mark.parametrize(
    "backend",
    [(kind, IdleConfig(max_conversations=1)) for kind in ("memory", "redis")],
    indirect=True,
)
async def test_backend_contract_capacity_does_not_evict_unresolved_activity(backend):
    key, _, _ = await seed(backend)
    with pytest.raises(Overloaded):
        await backend.open_session(
            replace(key, user_id=43, chat_id=43), lifetime_seconds=300, operation_id="overflow"
        )
    assert (await backend.load(key)).activity is not None


@pytest.mark.parametrize(
    "backend",
    [(kind, IdleConfig(max_tokens_per_conversation=1)) for kind in ("memory", "redis")],
    indirect=True,
)
async def test_backend_contract_token_capacity_and_prompt_pruning(backend):
    key, session, activity = await seed(backend)
    arguments = dict(activity_id=activity.activity_id, expires_at=session.expires_at)
    await backend.reserve_control(key, token="first", prompt_id="one", **arguments)
    with pytest.raises(Overloaded):
        await backend.reserve_control(key, token="second", prompt_id="one", **arguments)
    await backend.reserve_control(key, token="replacement", prompt_id="two", **arguments)
    assert await backend.resolve_control(key, "first") is None
    assert await backend.resolve_control(key, "replacement") is not None


@pytest.mark.parametrize(
    "backend",
    [
        (kind, IdleConfig(max_conversations=1, recovery_retention_seconds=0.03))
        for kind in ("memory", "redis")
    ],
    indirect=True,
)
async def test_backend_contract_expired_terminal_evidence_is_pruned_for_admission(backend):
    import asyncio

    key = IdleConversationKey("test", 1, 42, 42)
    await backend.open_session(key, lifetime_seconds=0.02, operation_id="short-session")
    await asyncio.sleep(0.06)
    other = replace(key, user_id=43, chat_id=43)
    accepted = await backend.open_session(
        other, lifetime_seconds=30, operation_id="after-retention"
    )
    assert accepted.session_id
    assert await backend.load(key) is None


async def test_backend_contract_replacement_keeps_retry_receipt_and_revokes_old_generation(backend):
    key, session, activity = await seed(backend)
    new = await backend.replace_session(
        key, expected=session.guard, lifetime_seconds=300, operation_id="replace"
    )
    assert new.session_id != session.session_id
    assert (
        await backend.replace_session(
            key, expected=session.guard, lifetime_seconds=300, operation_id="replace"
        )
        == new
    )
    with pytest.raises(ActivityConflict):
        await backend.clear(
            key, expected=activity.guard, operation_id="stale-clear", reason="cancel"
        )
    current = await backend.load(key)
    assert current.activity is None
    assert current.session == new
    assert current.idle.deadline is None
