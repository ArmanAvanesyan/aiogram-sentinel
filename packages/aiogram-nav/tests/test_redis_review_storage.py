"""Redis review regressions: sweep ownership and retained-evidence consistency."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from aiogram_nav import (
    EffectCheckpoint,
    MessageRef,
    NavigationConfig,
    NavigationIntent,
    PersistenceUnavailable,
    RenderResult,
    SchemaUnsupported,
    StaleView,
)
from aiogram_nav.codec import decode, encode
from aiogram_nav.storage.redis import RedisNavigationRepository
from aiogram_nav.storage.redis_scripts import SCAN_PAGE
from tests.test_redis_backend import KEY, enter
from tests.test_redis_backend import repository as parity_repository


async def repository(client, **config):
    repo = RedisNavigationRepository(
        redis=client, prefix=f"review-storage:{uuid4().hex}", config=NavigationConfig(**config)
    )
    await repo.initialize()
    return repo


@pytest.mark.parametrize("damage", ["live", "profile", "established"])
async def test_sweep_fails_closed_even_when_no_records_are_retained(nav_redis_client, damage):
    repo = await repository(nav_redis_client)
    await nav_redis_client.delete(f"{repo.prefix}:{damage}")
    with pytest.raises(PersistenceUnavailable):
        await repo.sweep()


async def test_concurrent_sweeps_serialize_shared_cursor_and_backlog(nav_redis_client, monkeypatch):
    repo = await repository(nav_redis_client, session_seconds=0.5, recovery_seconds=0.5)
    await enter(repo)
    await asyncio.sleep(1.1)
    original = repo._store.connection.script
    entered, release = asyncio.Event(), asyncio.Event()
    scans = 0

    async def held(source, keys, args, **kwargs):
        nonlocal scans
        if source == SCAN_PAGE:
            scans += 1
            if scans == 1:
                entered.set()
                await release.wait()
        return await original(source, keys, args, **kwargs)

    monkeypatch.setattr(repo._store.connection, "script", held)
    first = asyncio.create_task(repo.sweep())
    await entered.wait()
    second = asyncio.create_task(repo.sweep())
    await asyncio.sleep(0)
    assert scans == 1
    release.set()
    removed = await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
    assert sum(removed) == 1 and scans == 2


@pytest.mark.parametrize("damage", ["retention", "expiry", "state_only"])
async def test_corrupt_retained_receipts_cannot_extend_or_erase_recovery(nav_redis_client, damage):
    repo = await repository(nav_redis_client)
    await enter(repo)
    redis_key = repo._store.keys(KEY)[2]
    record = decode((await nav_redis_client.get(redis_key)).decode())
    receipt = record["operations"]["enter"]
    if damage == "retention":
        receipt["retention_until"] = -1
    elif damage == "expiry":
        result = receipt["result"]
        receipt["result"] = replace(
            result, snapshot=replace(result.snapshot, expires_at=result.snapshot.expires_at + 1)
        )
    else:
        receipt["prepared"] = None
    await nav_redis_client.set(redis_key, encode(record))
    with pytest.raises(SchemaUnsupported):
        await repo.lookup_operation(KEY, operation_id="enter")


async def test_corrupt_preparation_timeline_is_rejected_before_resume(nav_redis_client):
    repo = await repository(nav_redis_client)
    await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("pending", "main"))
    redis_key = repo._store.keys(KEY)[2]
    record = decode((await nav_redis_client.get(redis_key)).decode())
    receipt = record["operations"]["pending"]
    receipt["prepared"] = replace(receipt["prepared"], prepared_at=receipt["prepared"].expires_at)
    await nav_redis_client.set(redis_key, encode(record))
    with pytest.raises(SchemaUnsupported):
        await repo.pending(KEY)


async def test_corrupt_message_receipt_cannot_clean_up_another_conversation(nav_redis_client):
    repo = await repository(nav_redis_client)
    await enter(repo)
    redis_key = repo._store.keys(KEY)[2]
    record = decode((await nav_redis_client.get(redis_key)).decode())
    current = record["current"]
    view = replace(current.snapshot.view, messages=(MessageRef(43, 7),))
    record["current"] = replace(current, snapshot=replace(current.snapshot, view=view))
    await nav_redis_client.set(redis_key, encode(record))
    with pytest.raises(SchemaUnsupported):
        await repo.load(KEY)


# Reuse the same parametrized contract fixture for both mutation boundaries.
repository_backend = parity_repository


async def test_invalid_chat_receipt_rejected_before_persisting_evidence(repository_backend):
    repo = repository_backend
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("render", "main")
    )
    await repo.checkpoint(KEY, operation_id="render", effect=EffectCheckpoint("render", "started"))
    invalid = RenderResult(prepared.view_id, (MessageRef(43, 7),))
    with pytest.raises(StaleView):
        await repo.checkpoint(
            KEY,
            operation_id="render",
            effect=EffectCheckpoint("render", "confirmed", invalid),
        )
    pending = await repo.pending(KEY)
    assert pending.effects["render"].state == "started"
