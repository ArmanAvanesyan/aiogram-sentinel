"""The same ownership and replay contracts run on both engines and storage kinds."""

from uuid import uuid4

import pytest

from aiogram_nav import MemoryNavigationRepository, NavigationConfig
from tests import test_redis_backend as contracts


@pytest.fixture(
    params=[("memory", "python"), ("memory", "rust"), ("redis", "python"), ("redis", "rust")]
)
async def backend(request):
    kind, engine = request.param
    if engine == "rust":
        pytest.importorskip("aiogram_nav_native")
    config = NavigationConfig(engine=engine)
    client = None
    if kind == "memory":
        repo = MemoryNavigationRepository(config=config)
    else:
        from aiogram_nav.storage.redis import RedisNavigationRepository

        url = request.getfixturevalue("nav_redis_url")
        redis = request.getfixturevalue("nav_redis_module")
        client = redis.Redis.from_url(url)
        repo = RedisNavigationRepository(
            redis=client, prefix=f"parity3:{uuid4().hex}", config=config
        )
        await repo.initialize()
    await repo.activate_storage_format(
        target=3, operation_id="format3", dry_run=False, old_workers_drained=True
    )
    yield repo
    await repo.close()
    if client is not None:
        await client.aclose()


async def test_prepare_commit_replay(backend):
    await contracts.test_prepare_commit_and_retry_contract(backend)


async def test_concurrent_prepare(backend):
    await contracts.test_parallel_prepare_has_one_semantic_winner(backend)


async def test_partial_render_recovery(backend):
    await contracts.test_partial_render_evidence_and_confirmed_receipt_contract(backend)


async def test_actor_view_callback_ownership(backend):
    await contracts.test_callback_tokens_bind_actor_conversation_session_and_view(backend)
