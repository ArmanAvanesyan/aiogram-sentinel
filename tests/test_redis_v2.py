"""Format activation retains receipts and fences old storage generations."""

import json
from uuid import uuid4

import pytest
from aiogram_coordination import ExternalSession

from aiogram_nav import (
    CommitUnknown,
    ConfigurationError,
    NavigationIntent,
    OperationIdConflict,
    PendingAction,
    PersistenceUnavailable,
)
from aiogram_nav.storage.redis import RedisNavigationRepository
from aiogram_nav.storage.redis_migration import ACTIVATE
from tests.test_redis_backend import KEY, enter


async def repository(client, prefix=None):
    repo = RedisNavigationRepository(redis=client, prefix=prefix or f"format:{uuid4().hex}")
    await repo.initialize()
    return repo


async def test_activation_dry_run_preserves_all_namespace_bytes(nav_redis_client):
    repo = await repository(nav_redis_client)
    prepared, _ = await enter(repo)
    current = await repo.load(KEY)
    await repo.prepare(
        KEY, expected_version=current.version, intent=NavigationIntent("uncertain", "panel")
    )
    keys = await nav_redis_client.keys(f"{repo.prefix}:*")
    before = {key: await nav_redis_client.dump(key) for key in keys}
    report = await repo.activate_storage_format(operation_id="upgrade")
    assert report.before == 1 and report.after == 2 and not report.applied
    assert report.conversations == 1 and report.pending == 1
    assert set(await nav_redis_client.keys(f"{repo.prefix}:*")) == set(keys)
    assert before == {key: await nav_redis_client.dump(key) for key in keys}
    with pytest.raises(ConfigurationError, match="Drain"):
        await repo.activate_storage_format(operation_id="upgrade", dry_run=False)
    assert (
        await repo.lookup_operation(KEY, operation_id=prepared.operation_id)
    ).status == "completed"


async def test_activation_retains_pending_and_completed_receipts_fences_old_writers(
    nav_redis_client,
):
    repo = await repository(nav_redis_client)
    await enter(repo)
    stale = await repository(nav_redis_client, repo.prefix)
    previous = await repo.load(KEY)
    pending = await repo.prepare(
        KEY, expected_version=previous.version, intent=NavigationIntent("pending", "panel")
    )
    await repo.mark_unknown(KEY, operation_id="pending")
    record_key = repo._store.keys(KEY)[2]
    raw_before = await nav_redis_client.get(record_key)
    old_history = repo._store.history
    report = await repo.activate_storage_format(
        operation_id="upgrade", dry_run=False, old_workers_drained=True
    )
    assert report.applied and repo.storage_format == 2 and report.pending == 1
    assert await nav_redis_client.get(record_key) == raw_before
    assert repo._store.history.startswith(old_history + ":format2:")
    assert (await repo.lookup_operation(KEY, operation_id="enter")).status == "completed"
    assert (await repo.pending(KEY)).fingerprint == pending.fingerprint
    with pytest.raises(PersistenceUnavailable):
        await stale.load(KEY)
    # A 0.1 startup attempts the unchanged format-1 profile against the rotated one.
    from aiogram_nav.storage.redis_scripts import INITIALIZE

    assert (
        await nav_redis_client.eval(
            INITIALIZE,
            3,
            *repo._store.base_keys,
            f"{repo.prefix}:live",
            stale._store.profile,
            "old-worker",
        )
        == b"profile"
    )
    fresh = await repository(nav_redis_client, repo.prefix)
    assert fresh.storage_format == 2
    assert (await fresh.pending(KEY)).fingerprint == pending.fingerprint
    duplicate = await fresh.activate_storage_format(
        operation_id="upgrade", dry_run=False, old_workers_drained=True
    )
    assert duplicate.applied
    with pytest.raises(OperationIdConflict):
        await fresh.activate_storage_format(
            operation_id="another", dry_run=False, old_workers_drained=True
        )


async def test_external_binding_and_v2_writes_are_atomic_and_retain_uncertainty(nav_redis_client):
    repo = await repository(nav_redis_client)
    await repo.activate_storage_format(
        operation_id="upgrade", dry_run=False, old_workers_drained=True
    )
    expiry = repo.clock.now() + 100000
    async with repo.coordinator.hold(KEY):
        await repo.bind_external_session(
            KEY,
            ExternalSession("external", "1", expiry),
            coordination_scope=repo.coordinator.scope_token(KEY),
        )
    assert (await repo.external_session(KEY)).absolute_expires_at == expiry
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("pending", "main")
    )
    assert prepared.expires_at == expiry
    raw = await nav_redis_client.get(repo._store.keys(KEY)[2])
    assert json.loads(raw)["schema_version"] == 2
    with pytest.raises(PendingAction):
        await repo.bind_external_session(KEY, ExternalSession("next", "1", expiry + 10000))
    assert (await repo.pending(KEY)).session_id == prepared.session_id
    restored = await repository(nav_redis_client, repo.prefix)
    assert (await restored.external_session(KEY)).session_id == "external"


async def test_activation_lost_reply_recovers_same_operation(nav_redis_client, monkeypatch):
    repo = await repository(nav_redis_client)
    original = repo._store.connection.script
    lost = False

    async def script(source, keys, args, **kwargs):
        nonlocal lost
        result = await original(source, keys, args, **kwargs)
        if source == ACTIVATE and not lost:
            lost = True
            raise CommitUnknown("reply lost")
        return result

    monkeypatch.setattr(repo._store.connection, "script", script)
    with pytest.raises(CommitUnknown):
        await repo.activate_storage_format(
            operation_id="same", dry_run=False, old_workers_drained=True
        )
    result = await repo.activate_storage_format(
        operation_id="same", dry_run=False, old_workers_drained=True
    )
    assert result.applied and repo.storage_format == 2


async def test_activation_refuses_live_local_scopes(nav_redis_client):
    repo = await repository(nav_redis_client)
    async with repo.coordinator.hold(KEY):
        with pytest.raises(ConfigurationError, match="Drain"):
            await repo.activate_storage_format(
                operation_id="upgrade", dry_run=False, old_workers_drained=True
            )


async def test_manifest_damage_is_not_treated_as_an_empty_namespace(nav_redis_client):
    repo = await repository(nav_redis_client)
    await repo.activate_storage_format(
        operation_id="upgrade", dry_run=False, old_workers_drained=True
    )
    await nav_redis_client.delete(f"{repo.prefix}:storage-format")
    with pytest.raises(ConfigurationError):
        await repository(nav_redis_client, repo.prefix)


async def test_pristine_dry_run_does_not_bootstrap_namespace(nav_redis_client):
    repo = RedisNavigationRepository(redis=nav_redis_client, prefix=f"pristine:{uuid4().hex}")
    assert await nav_redis_client.keys(f"{repo.prefix}:*") == []
    report = await repo.activate_storage_format(operation_id="assessment")
    assert report.conversations == 0 and report.pending == 0 and not report.applied
    assert await nav_redis_client.keys(f"{repo.prefix}:*") == []


async def test_cli_assessment_is_read_only_and_apply_requires_explicit_drain(
    nav_redis_client, nav_redis_url
):
    import asyncio
    import sys
    from pathlib import Path

    prefix = f"cli:{uuid4().hex}"
    tool = Path(__file__).parents[1] / "tools" / "migrate_storage.py"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(tool),
        "--redis-url",
        nav_redis_url,
        "--prefix",
        prefix,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr
    assert json.loads(stdout) == {
        "before": 1,
        "after": 2,
        "applied": False,
        "conversations": 0,
        "pending": 0,
    }
    assert await nav_redis_client.keys(f"{prefix}:*") == []
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(tool),
        "--redis-url",
        "redis://private:do-not-log@localhost",
        "--apply",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    assert process.returncode == 2 and b"requires" in stderr and b"do-not-log" not in stderr


async def test_activated_namespace_accepts_new_read_only_assessment(nav_redis_client):
    repo = await repository(nav_redis_client)
    await repo.activate_storage_format(
        operation_id="apply", dry_run=False, old_workers_drained=True
    )
    report = await repo.activate_storage_format(operation_id="later-assessment")
    assert report.before == report.after == 2 and not report.applied
