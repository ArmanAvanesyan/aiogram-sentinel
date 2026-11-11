"""Cold migration is bounded, fenced, resumable and preserves original recovery."""

import asyncio
import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import pytest

from aiogram_idle import IdleConfig, IdleConversationKey, PromptPolicy
from aiogram_idle.errors import BackendInconsistent, ConfigurationMismatch
from aiogram_idle.models import IdleSnapshot, PendingOperation, Phase
from aiogram_idle.storage.cold import keys, receipt_key
from aiogram_idle.storage.cold_backup import (
    cleanup_backup,
    export_backup,
    inspect_backup,
    list_backups,
)
from aiogram_idle.storage.cold_migration import backup_keys, migrate, migration_key
from aiogram_idle.storage.cold_migration_scripts import COPY
from aiogram_idle.storage.redis import RedisIdleBackend

KEY = IdleConversationKey("cold-migration", 1, 42, 42)


async def legacy(client, *, replay=3600, pending=False, opaque=True):
    backend = RedisIdleBackend(
        redis=client,
        prefix="test:cold:migrate:" + uuid4().hex,
        config=IdleConfig(replay_retention_seconds=replay),
    )
    session = await backend.open_session(KEY, lifetime_seconds=60, operation_id="001-open")
    activity = await backend.enter(
        KEY,
        "form",
        policy_id="form",
        policy=PromptPolicy(),
        adapter_key="form",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="002-enter",
    )
    for index in range(3):
        activity = await backend.touch(
            KEY, expected=activity.guard, operation_id=f"003-touch-{index}"
        )
    current = await backend.load(KEY)
    operation = (
        PendingOperation(
            "uncertain", "prompt", started_at=backend.clock.now(), effects={"ask": "unknown"}
        )
        if pending
        else None
    )
    original = await backend.transition(
        KEY,
        expected_version=current.version,
        operation_id="snapshot",
        fingerprint="original-snapshot",
        transform=lambda old: replace(
            old,
            components={"application": {"nested": ["original", 1]}} if opaque else {},
            idle=IdleSnapshot(
                phase=Phase.EFFECT_UNKNOWN if pending else Phase.DISARMED, operation=operation
            ),
        ),
    )
    await backend.activate_storage_format(
        operation_id="format2", old_workers_drained=True, dry_run=False
    )
    await backend.activate_storage_format(
        expected=2, target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    return backend, session, original


async def finish(backend, *, limit=2):
    for _ in range(50):
        page = await migrate(backend._store, KEY, limit=limit, dry_run=False)
        if page.done:
            return page
    raise AssertionError("bounded migration failed to progress")


async def test_staged_migration_keeps_source_until_final_cutover_and_original_results(redis_client):
    backend, session, original = await legacy(redis_client)
    store = backend._store
    source = await redis_client.get(store.keys(KEY)[0])
    assessment = await migrate(store, KEY, limit=1)
    assert assessment.dry_run and assessment.backup_bytes == len(source) and assessment.total == 6
    assert await redis_client.get(backup_keys(store, KEY)[0]) is None
    first = await migrate(store, KEY, limit=1, dry_run=False)
    assert not first.done and first.copied == 1
    assert await redis_client.get(store.keys(KEY)[0]) == source
    inspection = await inspect_backup(store, KEY)
    assert inspection.source_digest == hashlib.sha256(source).hexdigest()
    assert (
        await export_backup(store, KEY, expected_digest=inspection.source_digest)
    ).encode() == source
    cursor, seen = "0", []
    for _ in range(1000):
        page = await list_backups(store, cursor=cursor, limit=1000)
        seen.extend(page.items)
        cursor = page.cursor
        if cursor == "0":
            break
    assert len(seen) == 1 and seen[0].bytes == len(source)
    backup_deadline = await redis_client.execute_command("PEXPIRETIME", inspection.backup_key)
    await finish(backend)
    assert json.loads(await redis_client.get(store.keys(KEY)[0]))["kind"] == "idle-hot"
    assert await redis_client.get(store.keys(KEY)[0]) != source
    assert (
        await redis_client.execute_command("PEXPIRETIME", inspection.backup_key) == backup_deadline
    )
    assert await redis_client.exists(migration_key(store, KEY)) == 0
    assert await backend.open_session(KEY, lifetime_seconds=60, operation_id="001-open") == session

    def forbidden(_):
        raise AssertionError("original replay must not execute a new transition")

    replay = await backend.transition(
        KEY,
        expected_version=1,
        operation_id="snapshot",
        fingerprint="original-snapshot",
        transform=forbidden,
    )
    assert replay == original and replay.components["application"]["nested"] == ("original", 1)
    row = json.loads(await redis_client.get(receipt_key(store, KEY, "snapshot")))
    assert row["result"] is None and len(row["result_ref"]) == 64
    assert await redis_client.get(
        store.prefix + ":result:" + store.ident(KEY) + ":" + row["result_ref"]
    )


async def test_pending_backup_and_pending_body_never_receive_automatic_ttl(redis_client):
    backend, _, original = await legacy(redis_client, replay=0.08, pending=True)
    await finish(backend)
    info = await inspect_backup(backend._store, KEY)
    assert info.protected and info.expires_at is None
    assert await redis_client.pttl(info.backup_key) == -1
    assert await redis_client.pttl(keys(backend._store, KEY)[0]) == -1
    await asyncio.sleep(0.12)
    assert (await backend.load(KEY)).idle.operation == original.idle.operation
    assert await inspect_backup(backend._store, KEY) == info
    with pytest.raises(ConfigurationMismatch):
        await cleanup_backup(backend._store, KEY, expected_digest=info.source_digest)
    assert await cleanup_backup(
        backend._store,
        KEY,
        expected_digest=info.source_digest,
        canonical_rows_verified=True,
        unresolved_evidence_preserved=True,
    )
    assert await inspect_backup(backend._store, KEY) is None
    assert await redis_client.pttl(keys(backend._store, KEY)[0]) == -1
    assert (await backend.load(KEY)).idle.operation == original.idle.operation


async def test_backup_cleanup_flags_cannot_override_missing_promised_canonical_row(redis_client):
    backend, _, _ = await legacy(redis_client, pending=True)
    await finish(backend)
    info = await inspect_backup(backend._store, KEY)
    await redis_client.delete(receipt_key(backend._store, KEY, "001-open"))
    with pytest.raises(BackendInconsistent):
        await cleanup_backup(
            backend._store,
            KEY,
            expected_digest=info.source_digest,
            canonical_rows_verified=True,
            unresolved_evidence_preserved=True,
        )
    assert await redis_client.pttl(info.backup_key) == -1


async def test_backup_and_contentaddressed_result_hash_corruption_fail_closed(redis_client):
    backend, _, _ = await legacy(redis_client, pending=True)
    await finish(backend)
    info = await inspect_backup(backend._store, KEY)
    await redis_client.append(info.backup_key, "corruption")
    with pytest.raises(BackendInconsistent):
        await inspect_backup(backend._store, KEY)
    row = json.loads(await redis_client.get(receipt_key(backend._store, KEY, "snapshot")))
    blob = backend._store.prefix + ":result:" + backend._store.ident(KEY) + ":" + row["result_ref"]
    await redis_client.set(blob, "corrupt", keepttl=True)
    with pytest.raises(BackendInconsistent):
        await backend.transition(
            KEY,
            expected_version=1,
            operation_id="snapshot",
            fingerprint="original-snapshot",
            transform=lambda old: old,
        )


async def test_lost_migration_copy_reply_resumes_from_durable_position(redis_client):
    lost = {"value": True}

    class ReplyLost:
        async def execute_command(self, *args):
            result = await redis_client.execute_command(*args)
            if (
                args[0] == "EVALSHA"
                and args[1] == hashlib.sha1(COPY.encode(), usedforsecurity=False).hexdigest()
                and lost["value"]
            ):
                lost["value"] = False
                raise ConnectionError("reply lost after copy committed")
            return result

    backend, session, _ = await legacy(ReplyLost())
    from aiogram_idle.errors import CommitUnknown

    with pytest.raises(CommitUnknown):
        await migrate(backend._store, KEY, limit=1, dry_run=False)
    page = await migrate(backend._store, KEY, limit=1, dry_run=False)
    assert page.copied == 2
    await finish(backend)
    assert await backend.open_session(KEY, lifetime_seconds=60, operation_id="001-open") == session


async def test_migration_source_change_never_overwrites_current_or_backup(redis_client):
    backend, _, _ = await legacy(redis_client)
    await migrate(backend._store, KEY, limit=1, dry_run=False)
    info = await inspect_backup(backend._store, KEY)
    key = backend._store.keys(KEY)[0]
    source = await redis_client.get(key)
    await redis_client.append(key, " ")  # still valid JSON, but not the assessed source
    from aiogram_idle.errors import VersionConflict

    with pytest.raises(VersionConflict):
        await migrate(backend._store, KEY, limit=1, dry_run=False)
    assert await redis_client.get(key) == source + b" "
    assert (
        await export_backup(backend._store, KEY, expected_digest=info.source_digest)
    ).encode() == source


async def test_migration_wrong_type_preflight_has_no_partial_copy(redis_client):
    armed = {"value": True}

    class WrongType:
        async def execute_command(self, *args):
            if (
                args[0] == "EVALSHA"
                and args[1] == hashlib.sha1(COPY.encode(), usedforsecurity=False).hexdigest()
                and armed["value"]
            ):
                armed["value"] = False
                await redis_client.hset(args[3 + 14], "unexpected", "hash")
            return await redis_client.execute_command(*args)

    backend, _, _ = await legacy(WrongType())
    source = await redis_client.get(backend._store.keys(KEY)[0])
    with pytest.raises(BackendInconsistent):
        await migrate(backend._store, KEY, limit=1, dry_run=False)
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source
    assert await redis_client.exists(backup_keys(backend._store, KEY)[0]) == 0
    assert await redis_client.exists(migration_key(backend._store, KEY)) == 0


async def test_missing_forward_pending_body_cannot_be_attested_away(redis_client):
    backend, _, _ = await legacy(redis_client, replay=0.08, pending=True)
    await finish(backend)
    info = await inspect_backup(backend._store, KEY)
    await asyncio.sleep(0.12)
    await redis_client.delete(keys(backend._store, KEY)[0])
    with pytest.raises(BackendInconsistent):
        await cleanup_backup(
            backend._store,
            KEY,
            expected_digest=info.source_digest,
            canonical_rows_verified=True,
            unresolved_evidence_preserved=True,
        )
    assert await redis_client.pttl(info.backup_key) == -1


async def test_staging_gc_is_bounded_and_keeps_incomplete_migration(redis_client):
    from aiogram_idle.storage.cold_migration_gc import sweep_staging

    backend, _, _ = await legacy(redis_client, replay=0.08, opaque=False)
    page = await migrate(backend._store, KEY, limit=1, dry_run=False)
    cursor, removed = "0", 0
    for _ in range(1000):
        result = await sweep_staging(backend._store, cursor=cursor, limit=1000)
        removed += result.removed
        cursor = result.cursor
        if cursor == "0":
            break
    assert removed == 0
    await finish(backend)
    await asyncio.sleep(0.12)
    await redis_client.hset(
        migration_key(backend._store, KEY),
        mapping={
            "source": page.source_digest,
            "position": page.total,
            "total": page.total,
            "key": backend._store.member(KEY),
        },
    )
    cursor, removed = "0", 0
    for _ in range(1000):
        result = await sweep_staging(backend._store, cursor=cursor, limit=1000)
        removed += result.removed
        cursor = result.cursor
        if cursor == "0":
            break
    assert removed == 1
    assert await redis_client.exists(migration_key(backend._store, KEY)) == 0


async def test_migration_ownership_loss_cannot_publish_any_copy(redis_client):
    from aiogram_idle.errors import OwnershipLost

    armed = {"value": True}

    class LoseFence:
        async def execute_command(self, *args):
            if (
                args[0] == "EVALSHA"
                and args[1] == hashlib.sha1(COPY.encode(), usedforsecurity=False).hexdigest()
                and armed["value"]
            ):
                armed["value"] = False
                await redis_client.delete(args[3 + 13])
            return await redis_client.execute_command(*args)

    backend, _, _ = await legacy(LoseFence())
    source = await redis_client.get(backend._store.keys(KEY)[0])
    with pytest.raises(OwnershipLost):
        await migrate(backend._store, KEY, limit=1, dry_run=False)
    assert await redis_client.get(backend._store.keys(KEY)[0]) == source
    assert await redis_client.exists(backup_keys(backend._store, KEY)[0]) == 0


async def test_completed_receipt_gc_cannot_remove_protected_pending_or_backup(redis_client):
    from aiogram_idle.storage.cold_gc import sweep

    backend, _, original = await legacy(redis_client, replay=0.08, pending=True)
    await finish(backend)
    info = await inspect_backup(backend._store, KEY)
    await asyncio.sleep(0.12)
    while await sweep(backend._store, limit=2):
        pass
    assert await redis_client.hlen(keys(backend._store, KEY)[1]) == 0
    assert (await backend.load(KEY)).idle.operation == original.idle.operation
    assert await redis_client.pttl(keys(backend._store, KEY)[0]) == -1
    assert await redis_client.pttl(info.backup_key) == -1


async def test_opaque_component_unknown_lifetime_keeps_one_protected_backup(redis_client):
    backend, _, _ = await legacy(redis_client, replay=0.08, pending=False)
    await finish(backend)
    info = await inspect_backup(backend._store, KEY)
    assert info.protected and info.expires_at is None
    assert info.original_replay_until > 0
    await asyncio.sleep(0.12)
    assert await redis_client.pttl(info.backup_key) == -1
    assert (await inspect_backup(backend._store, KEY)).source_digest == info.source_digest
    with pytest.raises(ConfigurationMismatch):
        await cleanup_backup(backend._store, KEY, expected_digest=info.source_digest)
    assert await cleanup_backup(
        backend._store,
        KEY,
        expected_digest=info.source_digest,
        canonical_rows_verified=True,
        unresolved_evidence_preserved=True,
    )
