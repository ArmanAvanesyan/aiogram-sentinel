"""Real Redis format-three rows have bounded hot state and commit-time TTL."""

import asyncio
import json
from uuid import uuid4

import pytest

from aiogram_idle import IdleConfig, IdleConversationKey, PromptPolicy
from aiogram_idle.errors import OperationIdConflict
from aiogram_idle.storage.cold import keys, receipt_key
from aiogram_idle.storage.redis import RedisIdleBackend

KEY = IdleConversationKey("cold", 1, 42, 42)


async def create(client, *, config=None):
    backend = RedisIdleBackend(redis=client, prefix="test:cold:" + uuid4().hex, config=config)
    await backend.initialize()
    await backend.activate_storage_format(
        operation_id="format2", old_workers_drained=True, dry_run=False
    )
    await backend.activate_storage_format(
        expected=2, target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    return backend


async def test_cold_receipts_exact_replay_and_hot_size_not_age(redis_client):
    backend = await create(redis_client)
    session = await backend.open_session(KEY, lifetime_seconds=100, operation_id="session")
    activity = await backend.enter(
        KEY,
        "draft",
        policy_id="draft",
        policy=PromptPolicy(),
        adapter_key="form",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="entry",
    )
    sizes = []
    original = activity
    for index in range(50):
        activity = await backend.touch(KEY, expected=activity.guard, operation_id=f"touch:{index}")
        sizes.append(len(await redis_client.get(backend._store.keys(KEY)[0])))
    assert max(sizes) - min(sizes) < 100
    assert (
        await backend.enter(
            KEY,
            "draft",
            policy_id="draft",
            policy=PromptPolicy(),
            adapter_key="form",
            params={},
            session_id=session.session_id,
            expires_at=session.expires_at,
            operation_id="entry",
        )
        == original
    )
    assert await redis_client.hlen(keys(backend._store, KEY)[1]) == 52
    raw = json.loads(await redis_client.get(backend._store.keys(KEY)[0]))
    assert raw["kind"] == "idle-hot"
    assert '"fingerprint"' not in raw["state"]
    assert await redis_client.pttl(receipt_key(backend._store, KEY, "entry")) > 0
    with pytest.raises(OperationIdConflict):
        await backend.open_session(KEY, lifetime_seconds=101, operation_id="session")


async def test_cold_lease_and_replay_lifetimes_are_separate(redis_client):
    backend = await create(redis_client, config=IdleConfig(replay_retention_seconds=0.08))
    session = await backend.open_session(KEY, lifetime_seconds=60, operation_id="open")
    row = receipt_key(backend._store, KEY, "open")
    ttl = await redis_client.pttl(row)
    await asyncio.sleep(0.03)
    assert await backend.open_session(KEY, lifetime_seconds=60, operation_id="open") == session
    assert await redis_client.pttl(row) < ttl
    await asyncio.sleep(0.08)
    assert await redis_client.get(row) is None
    assert (await backend.load(KEY)).session == session


async def test_cold_receipt_header_index_and_physical_expiry_are_identical(redis_client):
    backend = await create(redis_client)
    await backend.open_session(KEY, lifetime_seconds=60, operation_id="expiry")
    row_key = receipt_key(backend._store, KEY, "expiry")
    payload = json.loads(await redis_client.get(row_key))
    score = await redis_client.zscore(keys(backend._store, KEY)[2], "expiry")
    physical = await redis_client.execute_command("PEXPIRETIME", row_key)
    assert payload["expires_at"] == score == physical


@pytest.mark.parametrize("retention", [1e300, float(2**53) / 1000])
async def test_unsafe_cold_retention_cannot_mutate_any_namespace_state(redis_client, retention):
    from aiogram_idle.errors import ConfigurationMismatch

    backend = await create(redis_client, config=IdleConfig(replay_retention_seconds=retention))
    before = {
        name: await redis_client.dump(name)
        for name in await redis_client.keys(backend._store.prefix + ":*")
    }
    with pytest.raises(ConfigurationMismatch, match="exact"):
        await backend.open_session(KEY, lifetime_seconds=60, operation_id="unsafe")
    after = {
        name: await redis_client.dump(name)
        for name in await redis_client.keys(backend._store.prefix + ":*")
    }
    # Lua SCRIPT LOAD is server metadata, not application namespace state.
    assert after == before


async def test_lua_unsafe_retention_and_wrong_types_reject_before_hot_write(redis_client):
    import hashlib

    from aiogram_idle.errors import BackendInconsistent
    from aiogram_idle.storage.cold_scripts import COMMIT_COLD

    target = {"mode": "overflow"}

    class Intercept:
        async def execute_command(self, *args):
            if (
                args[0] == "EVALSHA"
                and args[1] == hashlib.sha1(COMMIT_COLD.encode(), usedforsecurity=False).hexdigest()
            ):
                values = list(args)
                key_count = int(values[2])
                if target["mode"] == "overflow":
                    offset = 3 + key_count + 14
                    payload = json.loads(values[offset])
                    payload["retention_ms"] = 1e300
                    values[offset] = json.dumps(payload)
                elif target["mode"] == "badheader":
                    offset = 3 + key_count + 14
                    payload = json.loads(values[offset])
                    payload["row"] = payload["row"][:-1] + ',"unknown":1e999}'
                    values[offset] = json.dumps(payload)
                else:
                    await redis_client.delete(values[3 + 13])
                    await redis_client.set(values[3 + 13], "wrong-type")
                return await redis_client.execute_command(*values)
            return await redis_client.execute_command(*args)

    backend = await create(Intercept())
    hot_key = backend._store.keys(KEY)[0]
    with pytest.raises(BackendInconsistent):
        await backend.open_session(KEY, lifetime_seconds=60, operation_id="overflow")
    assert await redis_client.get(hot_key) is None
    target["mode"] = "badheader"
    with pytest.raises(BackendInconsistent):
        await backend.open_session(KEY, lifetime_seconds=60, operation_id="invalid-header")
    assert await redis_client.get(hot_key) is None
    target["mode"] = "wrongtype"
    with pytest.raises(BackendInconsistent):
        await backend.open_session(KEY, lifetime_seconds=60, operation_id="wrongtype")
    assert await redis_client.get(hot_key) is None


async def test_receipt_gc_is_bounded_and_does_not_require_activity(redis_client):
    from aiogram_idle.storage.cold_gc import sweep

    backend = await create(redis_client, config=IdleConfig(replay_retention_seconds=0.03))
    session = await backend.open_session(KEY, lifetime_seconds=60, operation_id="open")
    activity = await backend.enter(
        KEY,
        "flow",
        policy_id="flow",
        policy=PromptPolicy(),
        adapter_key="flow",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
    )
    for index in range(6):
        activity = await backend.touch(KEY, expected=activity.guard, operation_id=f"touch:{index}")
    await asyncio.sleep(0.05)
    metadata = keys(backend._store, KEY)[1]
    original = await redis_client.hlen(metadata)
    assert original > 0
    assert await sweep(backend._store, limit=2) == min(2, original)
    assert await redis_client.hlen(metadata) == original - min(2, original)
    while await sweep(backend._store, limit=2):
        pass
    assert await redis_client.hlen(metadata) == 0
    assert await redis_client.zcard(keys(backend._store, KEY)[2]) == 0
    assert await redis_client.zcard(backend._store.prefix + ":receipt-sweep") == 0
    assert (await backend.load(KEY)).session == session


async def test_missing_promised_result_and_receipt_fail_closed(redis_client):
    from aiogram_idle.errors import BackendInconsistent

    backend = await create(redis_client)
    await backend.open_session(KEY, lifetime_seconds=60, operation_id="open")
    row = receipt_key(backend._store, KEY, "open")
    await redis_client.delete(row)
    with pytest.raises(BackendInconsistent):
        await backend.open_session(KEY, lifetime_seconds=60, operation_id="open")


async def test_exact_ttl_above_lua_json_number_precision(redis_client):
    backend = await create(redis_client, config=IdleConfig(replay_retention_seconds=9e12))
    await backend.open_session(KEY, lifetime_seconds=60, operation_id="large-safe-deadline")
    row_key = receipt_key(backend._store, KEY, "large-safe-deadline")
    header = json.loads(await redis_client.get(row_key))
    assert header["expires_at"] > 10**15
    assert header["expires_at"] == await redis_client.zscore(
        keys(backend._store, KEY)[2], "large-safe-deadline"
    )
    assert header["expires_at"] == await redis_client.execute_command("PEXPIRETIME", row_key)


async def test_shared_snapshot_blob_keeps_longest_reference_without_duplicate_renewal(redis_client):
    from dataclasses import replace

    backend = await create(redis_client, config=IdleConfig(replay_retention_seconds=0.3))
    await backend.open_session(KEY, lifetime_seconds=60, operation_id="open")
    before = await backend.load(KEY)
    original = await backend.transition(
        KEY,
        expected_version=before.version,
        operation_id="snapshot",
        fingerprint="snapshot",
        transform=lambda old: replace(old, components={"application": {"nested": ["value"]}}),
    )

    async def memoize(operation_id):
        async def reduce(engine):
            duplicate = engine._receipts.prepare(
                KEY, operation_id, "same-result", now=engine._now()
            )
            return (
                duplicate
                if duplicate is not None
                else engine._receipts.save(
                    KEY, operation_id, "same-result", original, now=engine._now()
                )
            )

        return await backend._store.mutate(KEY, reduce, operation_id=operation_id)

    assert await memoize("one") == original
    first = json.loads(await redis_client.get(receipt_key(backend._store, KEY, "one")))
    await asyncio.sleep(0.04)
    assert await memoize("two") == original
    second = json.loads(await redis_client.get(receipt_key(backend._store, KEY, "two")))
    assert first["result_ref"] == second["result_ref"]
    blob = (
        backend._store.prefix + ":result:" + backend._store.ident(KEY) + ":" + first["result_ref"]
    )
    assert await redis_client.execute_command("PEXPIRETIME", blob) == second["expires_at"]
    assert await memoize("one") == original
    assert await redis_client.execute_command("PEXPIRETIME", blob) == second["expires_at"]
    assert (
        json.loads(await redis_client.get(receipt_key(backend._store, KEY, "one")))["expires_at"]
        == first["expires_at"]
    )


async def test_expired_gc_rejects_foreign_row_proof_before_deletion(redis_client):
    from aiogram_idle.errors import BackendInconsistent
    from aiogram_idle.storage.cold_gc import sweep

    backend = await create(redis_client, config=IdleConfig(replay_retention_seconds=0.03))
    await backend.open_session(KEY, lifetime_seconds=60, operation_id="open")
    await asyncio.sleep(0.05)
    foreign = backend._store.prefix + ":foreign-evidence"
    await redis_client.set(foreign, "preserve")
    await redis_client.hset(keys(backend._store, KEY)[1], "open", foreign)
    with pytest.raises(BackendInconsistent):
        await sweep(backend._store)
    assert await redis_client.get(foreign) == b"preserve"


async def test_maximum_unicode_operation_id_replays_and_collects_exactly(redis_client):
    from aiogram_idle.storage.cold_gc import sweep

    backend = await create(redis_client, config=IdleConfig(replay_retention_seconds=0.08))
    operation_id = "🙂" * 256  # 256 codepoints, 1024 UTF-8 bytes; no normalization.
    session = await backend.open_session(KEY, lifetime_seconds=60, operation_id=operation_id)
    assert (
        await backend.open_session(KEY, lifetime_seconds=60, operation_id=operation_id) == session
    )
    await asyncio.sleep(0.12)
    assert await sweep(backend._store) == 1
    assert await redis_client.get(receipt_key(backend._store, KEY, operation_id)) is None


@pytest.mark.parametrize(
    "slot,expected",
    [(12, "string"), (13, "hash"), (14, "zset"), (15, "string"), (16, "string"), (17, "zset")],
)
async def test_every_cold_prefix_key_type_is_checked_before_hot_commit(
    redis_client, slot, expected
):
    import hashlib

    from aiogram_idle.errors import BackendInconsistent
    from aiogram_idle.storage.cold_scripts import COMMIT_COLD

    class Intercept:
        async def execute_command(self, *args):
            if (
                args[0] == "EVALSHA"
                and args[1] == hashlib.sha1(COMMIT_COLD.encode(), usedforsecurity=False).hexdigest()
            ):
                target = args[3 + slot - 1]
                await redis_client.delete(target)
                if expected == "string":
                    await redis_client.hset(target, "wrong", "hash")
                else:
                    await redis_client.set(target, "wrong-type")
            return await redis_client.execute_command(*args)

    backend = await create(Intercept())
    with pytest.raises(BackendInconsistent):
        await backend.open_session(KEY, lifetime_seconds=60, operation_id="must-not-commit")
    assert await redis_client.get(backend._store.keys(KEY)[0]) is None
