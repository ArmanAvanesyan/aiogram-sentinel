"""Component conversion preserves authoritative evidence through two bounded passes."""

import asyncio
import json

import pytest

from aiogram_idle.errors import BackendInconsistent, VersionConflict
from aiogram_idle.storage.canonical_migration import migrate, migration_key
from aiogram_idle.storage.canonical_redis import component_prefix, row_key
from tests.test_canonical_components import IDENTITY, delta, hot, row
from tests.test_cold_migration import KEY, finish, legacy


async def setup(client, *, duration=60000, replay=3600):
    backend, _, original = await legacy(client, replay=replay)
    await finish(backend)
    now = int(backend.clock.now() * 1000)
    payload = delta(
        None,
        "new",
        put={"one": row("one", "completed"), "pending": row("pending", "unknown")},
        duration={"one": duration},
        indexes={"t:one": "one", "t:pending": "pending"},
    )
    target = {"canonical": True, "revision": "new", "hot": hot("new"), "identity": IDENTITY}
    return (
        backend,
        original,
        dict(
            component="application",
            source_component=original.components["application"],
            target_component=target,
            ledger_delta=payload,
            absolute_expiry={"one": now + duration},
        ),
    )


async def complete(backend, kwargs, *, limit=1):
    pages = []
    for _ in range(20):
        page = await migrate(backend._store, KEY, **kwargs, limit=limit, dry_run=False)
        pages.append(page)
        if page.done:
            return pages
    raise AssertionError("migration never completed")


async def test_component_source_survives_copy_and_verify_pages(redis_client):
    backend, original, kwargs = await setup(redis_client)
    source = await redis_client.get(backend._store.keys(KEY)[0])
    first = await migrate(backend._store, KEY, **kwargs, limit=1, dry_run=False)
    assert first.copied == 1 and not first.done
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source
    second = await migrate(backend._store, KEY, **kwargs, limit=1, dry_run=False)
    assert second.copied == 2 and second.verified == 0 and not second.done
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source
    third = await migrate(backend._store, KEY, **kwargs, limit=1, dry_run=False)
    assert third.verified == 1 and not third.done
    progress = await redis_client.hgetall(migration_key(backend._store, KEY, "application"))
    assert b"proof:1" in progress
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source
    final = await migrate(backend._store, KEY, **kwargs, limit=1, dry_run=False)
    assert final.done and final.verified == 2
    loaded = await backend.load(KEY)
    assert loaded.session == original.session and loaded.activity == original.activity
    assert loaded.components["application"] == kwargs["target_component"]
    prefix = component_prefix(backend._store, KEY, "application")
    assert (
        await redis_client.execute_command("PEXPIRETIME", row_key(prefix, "one"))
        == kwargs["absolute_expiry"]["one"]
    )
    assert await redis_client.pttl(row_key(prefix, "pending")) == -1
    assert await redis_client.get(prefix + ":index-count") == b"2"
    assert await redis_client.exists(migration_key(backend._store, KEY, "application")) == 0
    assert (await migrate(backend._store, KEY, **kwargs, dry_run=False)).done


async def test_component_verification_rejects_missing_promised_row(redis_client):
    backend, _, kwargs = await setup(redis_client)
    await migrate(backend._store, KEY, **kwargs, limit=2, dry_run=False)
    source = await redis_client.get(backend._store.keys(KEY)[0])
    prefix = component_prefix(backend._store, KEY, "application")
    await redis_client.delete(row_key(prefix, "one"))
    with pytest.raises(BackendInconsistent):
        await migrate(backend._store, KEY, **kwargs, limit=2, dry_run=False)
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source


async def test_component_expired_terminal_body_may_be_absent(redis_client):
    backend, _, kwargs = await setup(redis_client, duration=10)
    await asyncio.sleep(0.02)
    await complete(backend, kwargs)
    prefix = component_prefix(backend._store, KEY, "application")
    assert await redis_client.get(row_key(prefix, "one")) is None
    assert await redis_client.zscore(prefix + ":expiry", "one") == kwargs["absolute_expiry"]["one"]


async def test_component_wrongtype_has_no_partial_copy(redis_client):
    backend, _, kwargs = await setup(redis_client)
    prefix = component_prefix(backend._store, KEY, "application")
    await redis_client.set(prefix + ":indexes", "wrong")
    source = await redis_client.get(backend._store.keys(KEY)[0])
    with pytest.raises(BackendInconsistent):
        await migrate(backend._store, KEY, **kwargs, limit=2, dry_run=False)
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source
    assert await redis_client.exists(row_key(prefix, "one")) == 0


async def test_component_target_change_cannot_resume_progress(redis_client):
    backend, _, kwargs = await setup(redis_client)
    await migrate(backend._store, KEY, **kwargs, limit=1, dry_run=False)
    payload = dict(kwargs["ledger_delta"])
    payload["put"] = dict(payload["put"])
    raw = json.loads(payload["put"]["one"])
    raw["integration_payload"] = "changed"
    payload["put"]["one"] = json.dumps(raw)
    with pytest.raises(VersionConflict):
        await migrate(
            backend._store, KEY, **dict(kwargs, ledger_delta=payload), limit=1, dry_run=False
        )


async def test_component_verification_proof_corruption_blocks_cutover(redis_client):
    backend, _, kwargs = await setup(redis_client)
    for _ in range(3):
        await migrate(backend._store, KEY, **kwargs, limit=1, dry_run=False)
    source = await redis_client.get(backend._store.keys(KEY)[0])
    await redis_client.hset(migration_key(backend._store, KEY, "application"), "proof:1", "0" * 64)
    with pytest.raises(BackendInconsistent):
        await migrate(backend._store, KEY, **kwargs, limit=1, dry_run=False)
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source


async def test_component_fence_loss_blocks_every_write(redis_client):
    from aiogram_idle.errors import OwnershipLost

    backend, _, kwargs = await setup(redis_client)
    old = backend._store.fencer

    def lost(key, *, scope=None):
        proof = old(key, scope=scope)
        return (proof[0], "not-the-owner") if proof else None

    backend._store.fencer = lost
    source = await redis_client.get(backend._store.keys(KEY)[0])
    with pytest.raises(OwnershipLost):
        await migrate(backend._store, KEY, **kwargs, limit=2, dry_run=False)
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source
    prefix = component_prefix(backend._store, KEY, "application")
    assert await redis_client.exists(prefix + ":metadata", row_key(prefix, "one")) == 0


async def test_component_dry_run_never_copies_or_changes_source(redis_client):
    backend, _, kwargs = await setup(redis_client)
    source = await redis_client.get(backend._store.keys(KEY)[0])
    page = await migrate(backend._store, KEY, **kwargs, limit=1)
    assert page.dry_run and page.copied == 1 and not page.done
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source
    assert await redis_client.exists(migration_key(backend._store, KEY, "application")) == 0


async def test_component_active_copy_blocks_source_cleanup_even_with_attestation(redis_client):
    from aiogram_idle.errors import ConfigurationMismatch
    from aiogram_idle.storage.cold_backup import cleanup_backup, inspect_backup

    backend, _, kwargs = await setup(redis_client, replay=0.01)
    await migrate(backend._store, KEY, **kwargs, limit=1, dry_run=False)
    await asyncio.sleep(0.02)
    inspection = await inspect_backup(backend._store, KEY)
    with pytest.raises(ConfigurationMismatch, match="canonical component copy"):
        await cleanup_backup(
            backend._store,
            KEY,
            expected_digest=inspection.source_digest,
            canonical_rows_verified=True,
            unresolved_evidence_preserved=True,
        )
    assert (await inspect_backup(backend._store, KEY)).protected
