"""Lost membership requires explicit bounded administrative recovery."""

from uuid import uuid4

from aiogram_idle.storage.redis import RedisIdleBackend
from tests.test_redis_backend import make_due, seed


async def test_missing_live_and_due_indexes_recover_without_effects(redis_client):
    prefix = f"test-admin:{uuid4().hex}"
    backend = RedisIdleBackend(redis=redis_client, prefix=prefix)
    await backend.initialize()
    key, _, activity = await seed(backend)
    await make_due(backend, key)
    keys = backend._store.keys(key)
    await redis_client.delete(keys[2], keys[3], keys[5], f"{prefix}:expiry")
    assert await backend.claim_due(limit=1, lease_seconds=5) == []
    assert await backend.reconcile(limit=1) == 0
    page = await backend.recover_indexes(limit=1)
    # SCAN may visit unrelated keys on this shared disposable server.
    for _ in range(10000):
        if page.complete:
            break
        page = await backend.recover_indexes(limit=1)
    else:
        raise AssertionError("administrative scan did not complete")
    claims = await backend.claim_due(limit=1, lease_seconds=5)
    assert len(claims) == 1 and claims[0].key == key
    assert (await backend.load(key)).activity == activity
    assert await redis_client.sismember(keys[3], backend._store.member(key))
    assert await redis_client.zscore(f"{prefix}:expiry", backend._store.member(key)) is not None


async def test_admin_scan_drains_overflow_without_dropping_records(redis_client):
    prefix = f"test-admin:{uuid4().hex}"
    backend = RedisIdleBackend(redis=redis_client, prefix=prefix)
    await backend.initialize()
    key, _, _ = await seed(backend)
    record_key = backend._store.keys(key)[0]
    # SSCAN/SCAN COUNT is a hint. A backend page buffers extra returned keys.
    backend._index_recovery.pending = [record_key, record_key, record_key]
    backend._index_recovery.cursor = "0"
    for remaining in [2, 1, 0]:
        page = await backend.recover_indexes(limit=1)
        assert page.inspected == 1 and page.pending == remaining
        assert page.complete is (remaining == 0)
