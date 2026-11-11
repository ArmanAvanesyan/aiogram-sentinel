"""Identical repository invariants against memory and a real Redis primary."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from aiogram_nav.config import NavigationConfig
from aiogram_nav.errors import OperationIdConflict, PendingAction, RenderUnknown, StaleView
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

KEY = ConversationKey("test", 1, 42, 42)


@pytest.fixture(params=["memory", "redis"])
async def repository(request):
    client = None
    kind, config = (
        request.param if isinstance(request.param, tuple) else (request.param, NavigationConfig())
    )
    if kind == "memory":
        instance = MemoryNavigationRepository(config=config)
    else:
        url = request.getfixturevalue("nav_redis_url")
        redis = request.getfixturevalue("nav_redis_module")

        from aiogram_nav.storage.redis import RedisNavigationRepository

        client = redis.Redis.from_url(url)
        instance = RedisNavigationRepository(
            redis=client, prefix=f"test:nav:{uuid4().hex}", config=config
        )
        await instance.initialize()
    yield instance
    await instance.close()
    if client is not None:
        await client.aclose()


async def enter(repo, node="main", operation_id="enter"):
    previous = await repo.load(KEY)
    version = previous.version if previous else None
    prepared = await repo.prepare(
        KEY,
        expected_version=version,
        intent=NavigationIntent(operation_id, node),
    )
    committed = await repo.commit(
        KEY,
        expected_version=version,
        mutation=NavigationMutation(
            operation_id, prepared.session_id, RenderResult(prepared.view_id)
        ),
    )
    return prepared, committed


async def test_prepare_commit_and_retry_contract(repository):
    prepared, first = await enter(repository)
    retried = await repository.prepare(
        KEY,
        expected_version=None,
        intent=NavigationIntent("enter", "main"),
    )
    assert retried.session_id == prepared.session_id
    duplicate = await repository.commit(
        KEY,
        expected_version="stale",
        mutation=NavigationMutation("enter", prepared.session_id, RenderResult(prepared.view_id)),
    )
    assert duplicate.duplicate and duplicate.snapshot == first.snapshot
    with pytest.raises(OperationIdConflict):
        await repository.prepare(
            KEY,
            expected_version=None,
            intent=NavigationIntent("enter", "wrong"),
        )
    _, second = await enter(repository, "panel", "second")
    assert second.snapshot.nav_revision == 2
    assert second.snapshot.activity_revision == 2
    assert second.snapshot.expires_at == first.snapshot.expires_at
    assert second.snapshot.history[0].node_id == "main"
    touched = await repository.commit(
        KEY,
        expected_version=second.version,
        mutation=NavigationMutation("touch", prepared.session_id, kind="touch"),
    )
    assert touched.snapshot.node_id == "panel"
    assert touched.snapshot.nav_revision == 2 and touched.snapshot.activity_revision == 3


async def test_parallel_prepare_has_one_semantic_winner(repository):
    results = await asyncio.gather(
        *(
            repository.prepare(KEY, expected_version=None, intent=NavigationIntent(str(i), "main"))
            for i in range(8)
        ),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, BaseException) for item in results) == 1
    assert sum(isinstance(item, PendingAction) for item in results) == 7


async def test_partial_render_evidence_and_confirmed_receipt_contract(repository):
    prepared = await repository.prepare(
        KEY,
        expected_version=None,
        intent=NavigationIntent("render", "main"),
    )
    await repository.checkpoint(
        KEY,
        operation_id="render",
        effect=EffectCheckpoint("message", "started"),
    )
    mutation = NavigationMutation("render", prepared.session_id, RenderResult(prepared.view_id))
    with pytest.raises(RenderUnknown):
        await repository.commit(KEY, expected_version=None, mutation=mutation)
    await repository.mark_unknown(KEY, operation_id="render")
    assert (await repository.lookup_operation(KEY, operation_id="render")).status == "unknown"
    receipt = EffectCheckpoint("message", "confirmed", {"message_id": 7})
    await repository.checkpoint(KEY, operation_id="render", effect=receipt)
    await repository.checkpoint(KEY, operation_id="render", effect=receipt)
    with pytest.raises(OperationIdConflict):
        await repository.checkpoint(
            KEY,
            operation_id="render",
            effect=replace(receipt, result={"message_id": 8}),
        )
    await repository.commit(KEY, expected_version=None, mutation=mutation)
    stored = await repository.lookup_operation(KEY, operation_id="render")
    assert stored.status == "completed" and stored.prepared.effects["message"] == receipt


async def test_callback_tokens_bind_actor_conversation_session_and_view(repository):
    prepared, result = await enter(repository)
    token = NavigationToken(
        "opaque",
        KEY,
        KEY.user_id,
        prepared.session_id,
        prepared.view_id,
        NavigationAction(target="panel"),
        result.snapshot.expires_at,
    )
    await repository.reserve_token(KEY, token, operation_id="reserve")
    assert await repository.resolve_token(replace(KEY, namespace="foreign"), token.token) is None
    with pytest.raises(StaleView):
        await repository.consume_token(KEY, token.token, actor_id=43, operation_id="foreign")
    assert (
        await repository.consume_token(KEY, token.token, actor_id=42, operation_id="accepted")
        == token
    )
    assert (
        await repository.consume_token(KEY, token.token, actor_id=42, operation_id="accepted")
        == token
    )
    with pytest.raises(StaleView):
        await repository.consume_token(KEY, token.token, actor_id=42, operation_id="replay")
    await enter(repository, "panel", "next-view")
    assert await repository.resolve_token(KEY, token.token) is None


@pytest.mark.parametrize(
    "repository",
    [(kind, NavigationConfig(session_seconds=0.15)) for kind in ("memory", "redis")],
    indirect=True,
)
async def test_expired_session_cannot_reauthorize_old_callback(repository):
    prepared, result = await enter(repository)
    token = NavigationToken(
        "expired-control",
        KEY,
        42,
        prepared.session_id,
        prepared.view_id,
        NavigationAction(target="panel"),
        result.snapshot.expires_at,
    )
    await repository.reserve_token(KEY, token, operation_id="reserve")
    await asyncio.sleep(0.2)
    assert await repository.load(KEY) is None
    assert await repository.resolve_token(KEY, token.token) is None
    fresh, _ = await enter(repository, "main", "fresh-session")
    assert fresh.session_id != prepared.session_id
    assert await repository.resolve_token(KEY, token.token) is None
