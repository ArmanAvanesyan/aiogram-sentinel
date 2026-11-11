"""A real legacy integrated ledger retains its original first activity result."""

import pytest

pytest.importorskip("aiogram_nav")

from uuid import uuid4

from aiogram_idle.integrations.nav.canonical import accepted_activity
from aiogram_idle.integrations.nav.canonical_migration import migrate
from aiogram_idle.storage.cold_migration import migrate as migrate_idle
from aiogram_idle.storage.redis import RedisIdleBackend
from tests.test_nav_runtime import make


async def test_legacy_nav_source_migrates_after_idle_envelope(redis_client):
    backend = RedisIdleBackend(redis=redis_client, prefix="nav:migration:" + uuid4().hex)
    integration, nav, screens, _, key = make(backend=backend)
    await nav.for_conversation(key).go("form", params={"draft_id": "kept"}, operation_id="original")
    repo = integration.navigation_repository
    idle_key = repo.mapping.to_idle(key)
    before = await backend.load(idle_key)
    original = before.components["aiogram_nav"]["activity_receipts"]["original"]
    await backend.activate_storage_format(
        operation_id="two", old_workers_drained=True, dry_run=False
    )
    await backend.activate_storage_format(
        expected=2, target=3, operation_id="three", old_workers_drained=True, dry_run=False
    )
    for _ in range(50):
        if (await migrate_idle(backend._store, idle_key, limit=2, dry_run=False)).done:
            break
    else:
        raise AssertionError("Idle migration stalled")
    for _ in range(50):
        if (await migrate(repo, key, limit=1, dry_run=False)).done:
            break
    else:
        raise AssertionError("Nav migration stalled")
    from aiogram_idle.storage.codec import decode

    assert await accepted_activity(repo, key, "original") == decode(original)
    after = await backend.load(idle_key)
    assert after.session == before.session and after.activity == before.activity
    assert "ledger" not in after.components["aiogram_nav"]
    assert "activity_receipts" not in after.components["aiogram_nav"]
    assert (await nav.for_conversation(key).current()).node_id == "form"
    assert screens.renders == ["form"]


async def test_legacy_unknown_render_remains_protected_without_resend(redis_client):
    from aiogram_nav import EffectCheckpoint

    backend = RedisIdleBackend(redis=redis_client, prefix="nav:migration:" + uuid4().hex)
    integration, nav, screens, _, key = make(backend=backend)
    pending = await nav.for_conversation(key).prepare_render(
        "form", params={"draft_id": "kept"}, operation_id="unknown"
    )
    repo = integration.navigation_repository
    await repo.checkpoint(key, operation_id="unknown", effect=EffectCheckpoint("render", "started"))
    await repo.checkpoint(key, operation_id="unknown", effect=EffectCheckpoint("render", "unknown"))
    idle_key = repo.mapping.to_idle(key)
    await backend.activate_storage_format(
        operation_id="two", old_workers_drained=True, dry_run=False
    )
    await backend.activate_storage_format(
        expected=2, target=3, operation_id="three", old_workers_drained=True, dry_run=False
    )
    for _ in range(50):
        if (await migrate_idle(backend._store, idle_key, limit=2, dry_run=False)).done:
            break
    for _ in range(50):
        if (await migrate(repo, key, limit=1, dry_run=False)).done:
            break
    else:
        raise AssertionError("Nav migration stalled")
    restored = await repo.pending(key)
    assert restored.operation_id == pending.operation_id
    assert restored.view_id == pending.view_id
    assert screens.renders == []
    from aiogram_idle.storage.canonical_redis import component_prefix, row_key

    prefix = component_prefix(backend._store, idle_key, "aiogram_nav")
    assert await redis_client.pttl(row_key(prefix, "unknown")) == -1
    assert await redis_client.sismember(prefix + ":protected", "unknown")
