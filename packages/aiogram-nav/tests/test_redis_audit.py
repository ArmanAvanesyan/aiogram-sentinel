"""Fail closed under index corruption, actual Lua errors and expiry races."""

import asyncio
from uuid import uuid4

import pytest

from aiogram_nav.codec import decode, encode
from aiogram_nav.errors import (
    BackendInconsistent,
    PersistenceUnavailable,
    RenderUnknown,
    SchemaUnsupported,
    SessionExpired,
)
from aiogram_nav.models import ConversationKey, NavigationIntent
from aiogram_nav.storage.redis import RedisNavigationRepository
from aiogram_nav.storage.redis_scripts import COMMIT
from tests.test_nav_recovery import StagedPresenter
from tests.test_redis_backend import KEY, enter
from tests.test_redis_recovery import navigation


async def repository(client):
    repo = RedisNavigationRepository(redis=client, prefix=f"test-audit:{uuid4().hex}")
    await repo.initialize()
    return repo


async def test_missing_live_index_rejects_unknown_key_admission(nav_redis_client):
    repo = await repository(nav_redis_client)
    await enter(repo)
    await nav_redis_client.delete(f"{repo.prefix}:live")
    other = ConversationKey(KEY.namespace, KEY.bot_id, 43, 43)
    with pytest.raises(PersistenceUnavailable):
        await repo.prepare(other, expected_version=None, intent=NavigationIntent("new", "main"))
    assert await nav_redis_client.exists(repo._store.keys(other)[2]) == 0


@pytest.mark.parametrize("corruption", ["no_prepared", "completed", "orphan_pending"])
async def test_corrupt_pending_evidence_never_disappears_silently(nav_redis_client, corruption):
    repo = await repository(nav_redis_client)
    await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("unresolved", "main"))
    record_key = repo._store.keys(KEY)[2]
    raw = await nav_redis_client.get(record_key)
    decoded = decode(raw.decode())
    if corruption == "no_prepared":
        decoded["operations"]["unresolved"]["prepared"] = None
    elif corruption == "completed":
        decoded["operations"]["unresolved"]["status"] = "completed"
    else:
        decoded["pending_id"] = None
    await nav_redis_client.set(record_key, encode(decoded))
    with pytest.raises(SchemaUnsupported):
        await repo.pending(KEY)


async def test_server_expiry_between_read_and_prepare_commit_rejected(
    nav_redis_client, monkeypatch
):
    repo = await repository(nav_redis_client)
    original = repo._store.connection.script

    async def delayed(source, keys, args, **kwargs):
        if source == COMMIT:
            await asyncio.sleep(0.06)
        return await original(source, keys, args, **kwargs)

    monkeypatch.setattr(repo._store.connection, "script", delayed)
    expiry = repo.clock.now() + 30
    with pytest.raises(SessionExpired):
        await repo.prepare(
            KEY,
            expected_version=None,
            intent=NavigationIntent("expire", "main", expires_at=expiry),
        )
    assert await repo.load(KEY) is None


@pytest.mark.parametrize("receipt", ["started", "confirmed"])
async def test_actual_partial_lua_error_preserves_effect_evidence(
    nav_redis_client, monkeypatch, receipt
):
    repo = await repository(nav_redis_client)
    presenter = StagedPresenter()
    presenter.interrupt = False
    nav = navigation(repo, presenter)
    original = repo._store.connection.script
    injected = False

    async def partial_error(source, keys, args, **kwargs):
        nonlocal injected
        if (
            source == COMMIT
            and not injected
            and f'"state":"{receipt}"' in args[4]
            and '"stage":"message"' in args[4]
        ):
            injected = True
            # Execute a genuine Redis Lua runtime error after the record write.
            # Lua does not roll writes back. Preserve the production key/index
            # mutation, then force an actual server ResponseError.
            source = source.replace("return 'ok'", "return redis.call('NAV_AUDIT_UNKNOWN_COMMAND')")
        return await original(source, keys, args, **kwargs)

    monkeypatch.setattr(repo._store.connection, "script", partial_error)
    with pytest.raises((BackendInconsistent, RenderUnknown)):
        await nav.for_conversation(KEY).go("main", operation_id="render")
    assert injected
    sends = presenter.sends
    pending = await repo.pending(KEY)
    assert pending is not None
    assert pending.effects["message"].state == receipt
    restarted = RedisNavigationRepository(redis=nav_redis_client, prefix=repo.prefix)
    await restarted.initialize()
    recovered = navigation(restarted, presenter)
    if receipt == "started":
        with pytest.raises(RenderUnknown):
            await recovered.recover(KEY, operation_id="render")
        assert sends == 0
    else:
        await recovered.recover(KEY, operation_id="render")
        assert sends == 1
    assert presenter.sends == sends
