"""Explicit activation preserves retained state and fences old Redis writers."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest

from aiogram_idle.errors import BackendInconsistent, ConfigurationMismatch, OperationIdConflict
from aiogram_idle.models import IdleConversationKey, PendingOperation, Phase
from aiogram_idle.storage.codec import decode, encode
from aiogram_idle.storage.memory import MemoryIdleBackend
from tests.test_redis_backend import make_due, seed


@pytest.mark.parametrize(
    "arguments,error",
    [
        ({"expected": True}, ConfigurationMismatch),
        ({"target": 1}, ConfigurationMismatch),
        ({"operation_id": ""}, ValueError),
        ({"operation_id": 1}, ValueError),
        ({"dry_run": 1}, ValueError),
        ({"old_workers_drained": 1}, ValueError),
    ],
)
async def test_activation_contract_rejects_invalid_input(arguments, error):
    backend = MemoryIdleBackend()
    with pytest.raises(error):
        await backend.activate_storage_format(**({"operation_id": "assess"} | arguments))
    assert await backend.storage_format() == 1


async def test_memory_dry_run_and_activation_receipts_preserve_records():
    backend = MemoryIdleBackend()
    key, session, _ = await seed(backend)
    original = await backend.load(key)
    report = await backend.activate_storage_format(operation_id="activation")
    assert report.dry_run and not report.changed and report.records == 1
    assert await backend.storage_format() == 1
    with pytest.raises(ConfigurationMismatch):
        await backend.require_storage_format(2)
    with pytest.raises(ConfigurationMismatch, match="Drain"):
        await backend.activate_storage_format(operation_id="activation", dry_run=False)
    applied = await backend.activate_storage_format(
        operation_id="activation", old_workers_drained=True, dry_run=False
    )
    assert applied.changed and await backend.storage_format() == 2
    await backend.require_storage_format(2)
    assert await backend.load(key) == original
    assert await backend.open_session(key, lifetime_seconds=300, operation_id="open") == session
    assert not (await backend.activate_storage_format(operation_id="activation")).changed
    with pytest.raises(OperationIdConflict):
        await backend.activate_storage_format(operation_id="different")


async def test_memory_activation_refuses_active_claim_or_scope():
    backend = MemoryIdleBackend()
    key, _, _ = await seed(backend)
    await make_due(backend, key)
    claims = await backend.claim_due(limit=1, lease_seconds=30)
    with pytest.raises(ConfigurationMismatch, match="drain"):
        await backend.activate_storage_format(
            operation_id="activate", old_workers_drained=True, dry_run=False
        )
    await backend.release_claim(claims[0])
    async with backend.coordinator.hold(key):
        with pytest.raises(ConfigurationMismatch, match="drain"):
            await backend.activate_storage_format(
                operation_id="activate", old_workers_drained=True, dry_run=False
            )


def test_codec_explicit_versions_keep_identity_encoding_stable():
    key = IdleConversationKey("default", 1, 42, 42)
    old = encode(key)
    new = encode(key, schema_version=2)
    assert json.loads(old)["schema_version"] == 1
    assert json.loads(new)["schema_version"] == 2
    assert decode(old) == decode(new) == key
    assert encode(key) == old


async def test_redis_activation_fences_initialized_writers_and_preserves_evidence(redis_client):
    from aiogram_idle.storage.redis import RedisIdleBackend

    prefix = "activation:" + uuid4().hex
    backend = RedisIdleBackend(redis=redis_client, prefix=prefix)
    stale = RedisIdleBackend(redis=redis_client, prefix=prefix)
    await backend.initialize()
    await stale.initialize()
    key, session, activity = await seed(backend)
    record = await backend.load(key)
    operation = PendingOperation(
        operation_id="uncertain",
        kind="prompt",
        started_at=backend.clock.now(),
        effects={"question": "started"},
    )
    record = await backend.transition(
        key,
        expected_version=record.version,
        operation_id="reserve",
        fingerprint="reserve",
        transform=lambda old: replace(
            old, idle=replace(old.idle, operation=operation, phase=Phase.EFFECT_UNKNOWN)
        ),
    )
    token = await backend.reserve_control(
        key,
        token="migration-token",
        prompt_id="old-prompt",
        activity_id=activity.activity_id,
        expires_at=backend.clock.now() + 120,
    )
    before = await redis_client.get(backend._store.keys(key)[0])
    config = await redis_client.get(prefix + ":config")
    report = await backend.activate_storage_format(operation_id="activate")
    assert report.records == report.unresolved == 1
    assert await redis_client.get(backend._store.keys(key)[0]) == before
    assert await backend.storage_format() == 1
    await backend.activate_storage_format(
        operation_id="activate", old_workers_drained=True, dry_run=False
    )
    assert await backend.storage_format() == 2
    assert await backend.load(key) == record
    assert await redis_client.get(prefix + ":config") == config
    with pytest.raises(BackendInconsistent, match="history"):
        await stale.load(key)
    current = RedisIdleBackend(redis=redis_client, prefix=prefix)
    await current.initialize()
    assert await current.storage_format() == 2
    await current.require_storage_format(2)
    assert await current.load(key) == record
    pages = []
    cursor = "0"
    while True:
        page = await current.migrate_storage_records(cursor=cursor)
        pages.append(page)
        cursor = page.cursor
        if cursor == "0":
            break
    assert sum(page.inspected for page in pages) == 1
    assert sum(page.migrated for page in pages) == 0
    assert await redis_client.get(current._store.keys(key)[0]) == before
    pages = []
    cursor = "0"
    while True:
        page = await current.migrate_storage_records(cursor=cursor, dry_run=False)
        pages.append(page)
        cursor = page.cursor
        if cursor == "0":
            break
    assert sum(page.migrated for page in pages) == 1
    after = await redis_client.get(current._store.keys(key)[0])
    assert json.loads(after)["schema_version"] == 2
    assert decode(after.decode()) == decode(before.decode())
    assert await current.resolve_control(key, token.token) == token
    assert (await current.load(key)).idle.operation.effects["question"] == "started"
    assert await current.open_session(key, lifetime_seconds=300, operation_id="open") == session
    assert await current.load(key) == record
    assert await current.lookup_operation(key, "reserve") == await backend.lookup_operation(
        key, "reserve"
    )
    with pytest.raises(ConfigurationMismatch):
        await current.activate_storage_format(operation_id="down", expected=2, target=1)
    assert activity.activity_id == record.activity.activity_id


async def test_redis_activation_rejects_claims_and_lost_marker(redis_client):
    from aiogram_idle.storage.redis import RedisIdleBackend

    backend = RedisIdleBackend(redis=redis_client, prefix="activation:" + uuid4().hex)
    await backend.initialize()
    key, _, _ = await seed(backend)
    await make_due(backend, key)
    claim = (await backend.claim_due(limit=1, lease_seconds=30))[0]
    with pytest.raises(ConfigurationMismatch, match="drain"):
        await backend.activate_storage_format(
            operation_id="activate", old_workers_drained=True, dry_run=False
        )
    await backend.release_claim(claim)
    await backend.activate_storage_format(
        operation_id="activate", old_workers_drained=True, dry_run=False
    )
    await redis_client.delete(backend._store.prefix + ":storage-format")
    other = RedisIdleBackend(redis=redis_client, prefix=backend._store.prefix)
    with pytest.raises(ConfigurationMismatch):
        await other.initialize()


async def test_redis_activation_recovers_a_committed_but_lost_response(redis_client):
    from aiogram_idle.errors import CommitUnknown
    from aiogram_idle.storage.activation import _ACTIVATE
    from aiogram_idle.storage.redis import RedisIdleBackend

    backend = RedisIdleBackend(redis=redis_client, prefix="activation:" + uuid4().hex)
    await backend.initialize()
    await seed(backend)
    original = backend._store.connection.script
    lost = False

    async def uncertain(source, keys, args, **kwargs):
        nonlocal lost
        result = await original(source, keys, args, **kwargs)
        if source == _ACTIVATE and not lost:
            lost = True
            raise CommitUnknown("Injected lost activation reply")
        return result

    backend._store.connection.script = uncertain
    with pytest.raises(CommitUnknown):
        await backend.activate_storage_format(
            operation_id="activate", old_workers_drained=True, dry_run=False
        )
    result = await backend.activate_storage_format(
        operation_id="activate", old_workers_drained=True, dry_run=False
    )
    assert lost and not result.changed and await backend.storage_format() == 2


async def test_redis_activation_cas_detects_concurrent_admission(redis_client):
    from aiogram_idle.errors import VersionConflict
    from aiogram_idle.storage.activation import _ACTIVATE
    from aiogram_idle.storage.redis import RedisIdleBackend

    backend = RedisIdleBackend(redis=redis_client, prefix="activation:" + uuid4().hex)
    await backend.initialize()
    await seed(backend)
    original = backend._store.connection.script
    inserted = False

    async def admission(source, keys, args, **kwargs):
        nonlocal inserted
        if source == _ACTIVATE and not inserted:
            inserted = True
            await backend.open_session(
                IdleConversationKey("test", 1, 43, 43), lifetime_seconds=300, operation_id="other"
            )
        return await original(source, keys, args, **kwargs)

    backend._store.connection.script = admission
    with pytest.raises(VersionConflict):
        await backend.activate_storage_format(
            operation_id="activate", old_workers_drained=True, dry_run=False
        )
    assert await backend.storage_format() == 1
    await backend.activate_storage_format(
        operation_id="activate", old_workers_drained=True, dry_run=False
    )
    assert await backend.storage_format() == 2


async def test_record_migration_preserves_scan_overflow_in_bounded_cursor(redis_client):
    from aiogram_idle.storage.redis import RedisIdleBackend

    backend = RedisIdleBackend(redis=redis_client, prefix="activation:" + uuid4().hex)
    await backend.initialize()
    keys = [IdleConversationKey("test", 1, actor, actor) for actor in (42, 43, 44)]
    for key in keys:
        await backend.open_session(key, lifetime_seconds=300, operation_id=f"open:{key.user_id}")
    await backend.activate_storage_format(
        operation_id="activate", old_workers_drained=True, dry_run=False
    )
    original = backend._store.connection.call
    scan_calls = 0

    async def scan(*args, **kwargs):
        nonlocal scan_calls
        if args[0] == "SCAN":
            scan_calls += 1
            return [b"0", [backend._store.keys(key)[0].encode() for key in keys]]
        return await original(*args, **kwargs)

    backend._store.connection.call = scan
    cursor = "0"
    inspected = migrated = 0
    while True:
        page = await backend.migrate_storage_records(cursor=cursor, limit=1, dry_run=False)
        assert page.inspected <= 1
        inspected += page.inspected
        migrated += page.migrated
        cursor = page.cursor
        if cursor == "0":
            break
    assert scan_calls == 1 and inspected == migrated == 3
