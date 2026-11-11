"""Queue repair must not let orphaned or corrupt entries starve valid work."""

from uuid import uuid4

from aiogram_idle.models import IdleConversationKey
from aiogram_idle.storage.redis import RedisIdleBackend
from tests.test_redis_backend import make_due, seed


async def test_orphan_due_head_is_removed_before_claiming_healthy_work(redis_client):
    backend = RedisIdleBackend(redis=redis_client, prefix=f"queue-audit:{uuid4().hex}")
    await backend.initialize()
    key, _, _ = await seed(backend)
    await make_due(backend, key)
    orphan = IdleConversationKey(key.namespace, key.bot_id, 43, 43)
    due = backend._store.keys(key)[2]
    await redis_client.zadd(due, {backend._store.member(orphan): 0})
    await backend.claim_due(limit=1, lease_seconds=5)
    claims = await backend.claim_due(limit=1, lease_seconds=5)
    assert [claim.key for claim in claims] == [key]
    assert await redis_client.zscore(due, backend._store.member(orphan)) is None


async def test_missing_job_is_reconstructed_without_replaying_effects(redis_client):
    backend = RedisIdleBackend(redis=redis_client, prefix=f"queue-audit:{uuid4().hex}")
    await backend.initialize()
    key, _, activity = await seed(backend)
    await make_due(backend, key)
    await redis_client.delete(backend._store.keys(key)[1])
    await backend.claim_due(limit=1, lease_seconds=5)
    claims = await backend.claim_due(limit=1, lease_seconds=5)
    assert [claim.key for claim in claims] == [key]
    assert (await backend.load(key)).activity == activity


async def test_reconcile_parks_bad_record_and_repairs_remaining_batch(redis_client):
    backend = RedisIdleBackend(redis=redis_client, prefix=f"queue-audit:{uuid4().hex}")
    await backend.initialize()
    key, _, _ = await seed(backend)
    other = IdleConversationKey(key.namespace, key.bot_id, 43, 43)
    session = await backend.open_session(other, lifetime_seconds=300, operation_id="other-open")
    from aiogram_idle.policies import PromptPolicy

    await backend.enter(
        other,
        "form",
        policy_id="draft",
        policy=PromptPolicy(10, 20),
        adapter_key="form",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="other-enter",
        enabled=True,
    )
    await make_due(backend, other)
    await redis_client.set(backend._store.keys(key)[0], "broken-json")
    await redis_client.delete(backend._store.keys(other)[1], backend._store.keys(other)[2])
    backend._store.reconcile_pending = [backend._store.member(key), backend._store.member(other)]
    await backend.reconcile(limit=2)
    assert (await backend.inspect_parked())[1] == {key: "BackendInconsistent"}
    assert [claim.key for claim in await backend.claim_due(limit=1, lease_seconds=5)] == [other]
