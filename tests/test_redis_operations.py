"""Real server configuration, retention and uncertain transaction responses."""

import asyncio
from uuid import uuid4

import pytest

from aiogram_nav import (
    CommitUnknown,
    ConfigurationError,
    ConversationKey,
    NavigationConfig,
    NavigationIntent,
    NavigationMutation,
    Overloaded,
    PersistenceUnavailable,
    RenderResult,
)
from aiogram_nav.storage.redis import RedisNavigationRepository
from tests.test_redis_backend import KEY, enter


async def test_profile_never_overwritten_and_missing_witness_fails_closed(nav_redis_client):
    prefix = f"test:nav:{uuid4().hex}"
    repo = RedisNavigationRepository(redis=nav_redis_client, prefix=prefix)
    await repo.initialize()
    profile = await nav_redis_client.get(f"{prefix}:profile")
    incompatible = RedisNavigationRepository(
        redis=nav_redis_client, prefix=prefix, config=NavigationConfig(max_tokens=1)
    )
    with pytest.raises(ConfigurationError):
        await incompatible.initialize()
    assert await nav_redis_client.get(f"{prefix}:profile") == profile
    await nav_redis_client.delete(f"{prefix}:established")
    with pytest.raises(PersistenceUnavailable):
        await repo.load(KEY)
    with pytest.raises(PersistenceUnavailable):
        await RedisNavigationRepository(redis=nav_redis_client, prefix=prefix).initialize()


async def test_retention_reclaims_terminal_but_never_pending(nav_redis_client):
    config = NavigationConfig(session_seconds=0.03, recovery_seconds=0.03, max_conversations=1)
    repo = RedisNavigationRepository(
        redis=nav_redis_client, prefix=f"test:nav:{uuid4().hex}", config=config
    )
    await enter(repo)
    await asyncio.sleep(0.08)
    # Sentinel may occupy a page; bounded scanning eventually visits the record.
    removed = sum([await repo.sweep(limit=1) for _ in range(6)])
    assert removed == 1
    await repo.prepare(KEY, expected_version=None, intent=NavigationIntent("pending", "main"))
    await asyncio.sleep(0.08)
    assert sum([await repo.sweep(limit=1) for _ in range(6)]) == 0
    with pytest.raises(Overloaded):
        await repo.prepare(
            ConversationKey("other", 1, 42, 42),
            expected_version=None,
            intent=NavigationIntent("blocked", "main"),
        )
    assert (await repo.pending(KEY)).operation_id == "pending"


async def test_actual_commit_then_lost_response_recovers_same_receipt(nav_redis_client):
    class LoseResponse:
        armed = False

        async def execute_command(self, *args):
            value = await nav_redis_client.execute_command(*args)
            if self.armed and args[0] == "EVALSHA":
                self.armed = False
                raise ConnectionError("response deliberately discarded")
            return value

    wire = LoseResponse()
    repo = RedisNavigationRepository(redis=wire, prefix=f"test:nav:{uuid4().hex}")
    prepared = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("once", "main")
    )
    mutation = NavigationMutation("once", prepared.session_id, RenderResult(prepared.view_id))
    # Read also uses EVALSHA. Arm only the mutating script, by wrapping the store call.
    original = wire.execute_command
    discarded = False

    async def selective(*args):
        nonlocal discarded
        if not discarded and args[0] == "EVALSHA" and len(args) > 2 and args[2] == 5:
            discarded = True
            wire.armed = True
        return await original(*args)

    wire.execute_command = selective
    with pytest.raises(CommitUnknown):
        await repo.commit(KEY, expected_version=None, mutation=mutation)
    assert (await repo.lookup_operation(KEY, operation_id="once")).status == "completed"
    result = await repo.commit(KEY, expected_version="stale", mutation=mutation)
    assert result.duplicate and result.snapshot.node_id == "main"


async def test_owned_client_closes_and_supplied_client_survives(nav_redis_client, nav_redis_url):
    repo = await RedisNavigationRepository.from_url(nav_redis_url, prefix=f"test:nav:{uuid4().hex}")
    assert await repo.load(KEY) is None
    await repo.close()
    await repo.close()
    supplied = RedisNavigationRepository(redis=nav_redis_client, prefix=f"test:nav:{uuid4().hex}")
    await supplied.initialize()
    await supplied.close()
    assert await nav_redis_client.ping()
