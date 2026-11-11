"""Activated format-three storage keeps original receipts and protected uncertainty."""

from uuid import uuid4

import pytest

from aiogram_nav import NavigationConfig, PersistenceUnavailable
from aiogram_nav.storage.redis import RedisNavigationRepository
from aiogram_nav.storage.redis_codec import loads
from aiogram_nav.storage.redis_ledger import keys, operation_key
from tests.test_redis_backend import KEY, enter


async def repository(client):
    repo = RedisNavigationRepository(redis=client, prefix=f"format3:{uuid4().hex}")
    await repo.initialize()
    return repo


async def test_empty_activation_then_canonical_operations(nav_redis_client):
    repo = await repository(nav_redis_client)
    await repo.activate_storage_format(
        target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    assert repo.storage_format == 3
    first, result = await enter(repo)
    assert (await repo.lookup_operation(KEY, operation_id="enter")).result == result
    assert await nav_redis_client.pttl(operation_key(repo._store, KEY, "enter")) > 0
    assert (await repo.load(KEY)).snapshot.session_id == first.session_id
    await enter(repo, operation_id="second")
    # Historical result remains the first screen, never the latest projection.
    assert (await repo.lookup_operation(KEY, operation_id="enter")).result == result


async def test_lazy_split_preserves_absolute_replay_deadline_and_fences_old_writer(
    nav_redis_client,
):
    repo = await repository(nav_redis_client)
    _, result = await enter(repo)
    old = RedisNavigationRepository(redis=nav_redis_client, prefix=repo.prefix)
    await old.initialize()
    legacy_raw = await nav_redis_client.get(repo._store.keys(KEY)[2])
    deadline = loads(legacy_raw.decode(), KEY).operations["enter"].retention_until
    await repo.activate_storage_format(
        target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    await repo.activate_storage_format(target=3, operation_id="assessment", dry_run=True)
    assert await nav_redis_client.get(repo._store.keys(KEY)[2]) == legacy_raw
    with pytest.raises(PersistenceUnavailable):
        await old.load(KEY)
    assert (await repo.load(KEY)).snapshot == result.snapshot
    assert await nav_redis_client.zscore(keys(repo._store, KEY)[5], "enter") == deadline
    assert (await repo.lookup_operation(KEY, operation_id="enter")).result == result


async def test_lazy_split_protected_uncertainty_has_no_ttl(nav_redis_client):
    from aiogram_nav import NavigationIntent

    repo = await repository(nav_redis_client)
    pending = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("uncertain", "main")
    )
    await repo.mark_unknown(KEY, operation_id="uncertain")
    await repo.activate_storage_format(
        target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    current = await repo.pending(KEY)
    assert current.view_id == pending.view_id and current.status == "unknown"
    assert await nav_redis_client.pttl(operation_key(repo._store, KEY, "uncertain")) == -1
    assert await nav_redis_client.sismember(keys(repo._store, KEY)[7], "uncertain")


async def test_active_controls_outlive_terminal_replay_receipt(nav_redis_client):
    import asyncio

    from aiogram_nav import (
        NavigationAction,
        NavigationConfig,
        NavigationIntent,
        NavigationMutation,
        NavigationToken,
        RenderResult,
    )

    repo = RedisNavigationRepository(
        redis=nav_redis_client,
        prefix=f"format3:{uuid4().hex}",
        config=NavigationConfig(recovery_seconds=0.01),
    )
    await repo.initialize()
    await repo.activate_storage_format(
        target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    pending = await repo.prepare(
        KEY, expected_version=None, intent=NavigationIntent("screen", "main")
    )
    token = NavigationToken(
        "A" * 24,
        KEY,
        KEY.user_id,
        pending.session_id,
        pending.view_id,
        NavigationAction(target="main"),
        pending.expires_at,
    )
    await repo.reserve_token(KEY, token, operation_id="reserve")
    await repo.commit(
        KEY,
        expected_version=None,
        mutation=NavigationMutation("screen", pending.session_id, RenderResult(pending.view_id)),
    )
    await asyncio.sleep(0.03)
    assert await nav_redis_client.get(operation_key(repo._store, KEY, "screen")) is None
    assert await repo.resolve_token(KEY, token.token) == token
    assert (
        await repo.consume_token(KEY, token.token, actor_id=KEY.user_id, operation_id="control")
        == token
    )
    assert await nav_redis_client.hlen(keys(repo._store, KEY)[4]) == 0


async def test_paced_token_cycles_exceed_ten_times_capacity_without_index_growth(nav_redis_client):
    import asyncio

    from aiogram_nav import (
        NavigationAction,
        NavigationConfig,
        NavigationIntent,
        NavigationMutation,
        NavigationToken,
        RenderResult,
    )

    repo = RedisNavigationRepository(
        redis=nav_redis_client,
        prefix=f"format3:{uuid4().hex}",
        config=NavigationConfig(max_receipts=2, recovery_seconds=0.005),
    )
    await repo.initialize()
    await repo.activate_storage_format(
        target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    for index in range(25):
        current = await repo.load(KEY)
        pending = await repo.prepare(
            KEY,
            expected_version=current.version if current else None,
            intent=NavigationIntent(f"screen-{index}", "main"),
        )
        token = NavigationToken(
            f"{index:024d}",
            KEY,
            KEY.user_id,
            pending.session_id,
            pending.view_id,
            NavigationAction(target="main"),
            pending.expires_at,
        )
        await repo.reserve_token(KEY, token, operation_id=f"reserve-{index}")
        await repo.commit(
            KEY,
            expected_version=pending.expected_version,
            mutation=NavigationMutation(
                f"screen-{index}", pending.session_id, RenderResult(pending.view_id)
            ),
        )
        await asyncio.sleep(0.015)
        assert await nav_redis_client.hlen(keys(repo._store, KEY)[4]) <= 2
        assert await nav_redis_client.hlen(keys(repo._store, KEY)[6]) <= 4
    assert len(await nav_redis_client.keys(f"{repo._store.keys(KEY)[2]}:operation:*")) <= 2


async def test_expired_legacy_string_operation_id_can_be_explicitly_revalidated_and_reused(
    nav_redis_client,
):
    import asyncio

    from aiogram_nav import NavigationConfig

    repo = RedisNavigationRepository(
        redis=nav_redis_client,
        prefix=f"format3:{uuid4().hex}",
        config=NavigationConfig(recovery_seconds=0.005),
    )
    await repo.initialize()
    await repo.activate_storage_format(
        target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    first, result = await enter(repo)
    await asyncio.sleep(0.015)
    # Outside the advertised replay window, the producer must revalidate its source.
    current = await repo.load(KEY)
    assert current.snapshot.session_id == first.session_id
    second, new_result = await enter(repo)
    assert second.view_id != first.view_id
    assert new_result.snapshot.nav_revision == result.snapshot.nav_revision + 1


async def test_fresh_format3_bootstrap_is_atomic_and_existing_legacy_rejects(nav_redis_client):
    import asyncio

    from aiogram_nav import ConfigurationError

    prefix = f"fresh3:{uuid4().hex}"
    first = RedisNavigationRepository(redis=nav_redis_client, prefix=prefix, storage_format=3)
    second = RedisNavigationRepository(redis=nav_redis_client, prefix=prefix, storage_format=3)
    await asyncio.gather(first.initialize(), second.initialize())
    assert first.storage_format == second.storage_format == 3
    assert first._store.history == second._store.history
    assert await first.load(KEY) is None
    automatic = RedisNavigationRepository(redis=nav_redis_client, prefix=prefix)
    await automatic.initialize()
    assert automatic.storage_format == 3
    legacy = await repository(nav_redis_client)
    namespace = await nav_redis_client.keys(f"{legacy.prefix}:*")
    before = {key: await nav_redis_client.dump(key) for key in namespace}
    with pytest.raises(ConfigurationError, match="migration"):
        await RedisNavigationRepository(
            redis=nav_redis_client, prefix=legacy.prefix, storage_format=3
        ).initialize()
    assert before == {key: await nav_redis_client.dump(key) for key in namespace}


async def test_explicit_eager_conversion_is_bounded_and_resumable(nav_redis_client):
    from aiogram_nav import ConversationKey, NavigationIntent, NavigationMutation, RenderResult

    repo = await repository(nav_redis_client)
    identities = [ConversationKey("test", 1, user, user) for user in (42, 43, 44)]
    for key in identities:
        prepared = await repo.prepare(
            key, expected_version=None, intent=NavigationIntent("screen", "main")
        )
        await repo.commit(
            key,
            expected_version=None,
            mutation=NavigationMutation(
                "screen", prepared.session_id, RenderResult(prepared.view_id)
            ),
        )
    await repo.activate_storage_format(
        target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    cursor, converted = "0:0", 0
    for _ in range(20):
        page = await repo.migrate_storage_page(cursor=cursor, limit=1)
        assert page["inspected"] <= 1
        converted += page["converted"]
        if page["cursor"] is None:
            break
        cursor = page["cursor"]
    else:
        pytest.fail("Bounded migration cursor did not terminate")
    assert converted == 3
    for key in identities:
        assert b'"kind":"hot"' in await nav_redis_client.get(repo._store.keys(key)[2])


async def test_migration_on_unactivated_namespace_does_not_bootstrap_legacy_state(nav_redis_client):
    from aiogram_nav import ConfigurationError

    prefix = f"unactivated3:{uuid4().hex}"
    repo = RedisNavigationRepository(redis=nav_redis_client, prefix=prefix)
    with pytest.raises(ConfigurationError, match="Activate"):
        await repo.migrate_storage_page()
    assert not await nav_redis_client.keys(f"{prefix}:*")


@pytest.mark.parametrize("engine", ["python", "rust"])
@pytest.mark.parametrize("backend", ["memory", "redis"])
async def test_retained_view_generation_cannot_be_reused(nav_redis_client, engine, backend):
    from aiogram_nav import MemoryNavigationRepository, NavigationIntent, RenderResult, StaleView

    if engine == "rust":
        pytest.importorskip("aiogram_nav_native")
    config = NavigationConfig(engine=engine)
    repo = (
        MemoryNavigationRepository(config=config, storage_format=3)
        if backend == "memory"
        else RedisNavigationRepository(
            redis=nav_redis_client,
            prefix=f"view-proof:{uuid4().hex}",
            config=config,
            storage_format=3,
        )
    )
    for operation, view in (("first", "a"), ("second", "b")):
        current = await repo.load(KEY)
        await repo.adopt_render(
            KEY,
            expected_version=current.version if current else None,
            intent=NavigationIntent(operation, "main", action="track", view_id=view),
            rendered=RenderResult(view),
        )
    current = await repo.load(KEY)
    with pytest.raises(StaleView):
        await repo.adopt_render(
            KEY,
            expected_version=current.version,
            intent=NavigationIntent("third", "main", action="track", view_id="a"),
            rendered=RenderResult("a"),
        )
