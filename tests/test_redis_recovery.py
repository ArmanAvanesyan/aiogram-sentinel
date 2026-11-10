"""Cross-client render recovery and ownership without real Telegram traffic."""

import asyncio
from uuid import uuid4

import pytest

from aiogram_nav.config import NavigationConfig
from aiogram_nav.errors import PersistenceUnavailable, RenderUnknown
from aiogram_nav.models import NavigationAction, NavigationToken, Node
from aiogram_nav.navigation import Navigation
from aiogram_nav.registry import NavigationRegistry
from aiogram_nav.storage.redis import RedisNavigationRepository
from tests.test_nav_recovery import StagedPresenter
from tests.test_navigation import Presenter
from tests.test_redis_backend import KEY, enter


async def repository(client, prefix=None):
    repo = RedisNavigationRepository(
        redis=client,
        prefix=prefix or f"test:nav:{uuid4().hex}",
        config=NavigationConfig(),
    )
    await repo.initialize()
    return repo


def navigation(repo, presenter):
    return Navigation(
        registry=NavigationRegistry(
            roots={"main"},
            nodes=[
                Node("main", renderer="main"),
                Node("panel", parent="main", renderer="panel"),
            ],
        ),
        repository=repo,
        presenter=presenter,
        namespace=KEY.namespace,
    )


async def test_two_clients_concurrent_runtime_action_sends_once(nav_redis_client, nav_redis_url):
    from redis.asyncio import Redis

    prefix = f"test:nav:{uuid4().hex}"
    client = Redis.from_url(nav_redis_url, decode_responses=True)
    try:
        first = await repository(nav_redis_client, prefix)
        second = await repository(client, prefix)
        presenter = Presenter()
        left, right = navigation(first, presenter), navigation(second, presenter)
        await asyncio.gather(
            left.for_conversation(KEY).go("main", operation_id="same-action"),
            right.for_conversation(KEY).go("main", operation_id="same-action"),
        )
        assert len(presenter.requests) == 1
        assert (await second.load(KEY)).snapshot.node_id == "main"
    finally:
        await client.aclose()


async def test_partial_render_reconstruction_reuses_confirmed_send(nav_redis_client, nav_redis_url):
    from redis.asyncio import Redis

    prefix = f"test:nav:{uuid4().hex}"
    first = await repository(nav_redis_client, prefix)
    presenter = StagedPresenter()
    nav = navigation(first, presenter)
    with pytest.raises(RenderUnknown):
        await nav.for_conversation(KEY).go("main", operation_id="render")
    assert presenter.sends == 1
    client = Redis.from_url(nav_redis_url)
    try:
        second = await repository(client, prefix)
        recovered = navigation(second, presenter)
        await recovered.recover(KEY, operation_id="render")
        assert presenter.sends == 1
        assert (await second.load(KEY)).snapshot.node_id == "main"
    finally:
        await client.aclose()


async def test_unknown_delivery_is_not_blindly_repeated_after_reconnect(nav_redis_client):
    prefix = f"test:nav:{uuid4().hex}"
    presenter = Presenter()
    first = navigation(await repository(nav_redis_client, prefix), presenter)
    await first.for_conversation(KEY).go("main", operation_id="main")
    presenter.failure = TimeoutError("delivery response lost")
    with pytest.raises(RenderUnknown):
        await first.for_conversation(KEY).go("panel", operation_id="uncertain")
    presenter.failure = None
    second = navigation(await repository(nav_redis_client, prefix), presenter)
    with pytest.raises(RenderUnknown):
        await second.recover(KEY, operation_id="uncertain")
    assert len(presenter.requests) == 2
    assert (await second.repository.load(KEY)).snapshot.node_id == "main"
    assert (await second.repository.pending(KEY)).status == "unknown"


async def test_confirmed_render_survives_commit_failure(nav_redis_client, monkeypatch):
    prefix = f"test:nav:{uuid4().hex}"
    first = await repository(nav_redis_client, prefix)
    presenter = Presenter()
    nav = navigation(first, presenter)

    async def unavailable(*args, **kwargs):
        raise PersistenceUnavailable("completion unavailable")

    monkeypatch.setattr(first, "commit", unavailable)
    with pytest.raises(PersistenceUnavailable):
        await nav.for_conversation(KEY).go("main", operation_id="render")
    other = await repository(nav_redis_client, prefix)
    recovered = navigation(other, presenter)
    await recovered.recover(KEY, operation_id="render")
    assert len(presenter.requests) == 1
    assert (await other.load(KEY)).snapshot.node_id == "main"


async def test_callback_consumption_has_one_cross_client_winner(nav_redis_client, nav_redis_url):
    from redis.asyncio import Redis

    from aiogram_nav.errors import StaleView

    prefix = f"test:nav:{uuid4().hex}"
    first = await repository(nav_redis_client, prefix)
    prepared, result = await enter(first)
    token = NavigationToken(
        "owned",
        KEY,
        KEY.user_id,
        prepared.session_id,
        prepared.view_id,
        NavigationAction(target="panel"),
        result.snapshot.expires_at,
    )
    await first.reserve_token(KEY, token, operation_id="reserve")
    client = Redis.from_url(nav_redis_url)
    try:
        second = await repository(client, prefix)
        results = await asyncio.gather(
            first.consume_token(KEY, "owned", actor_id=42, operation_id="first"),
            second.consume_token(KEY, "owned", actor_id=42, operation_id="second"),
            return_exceptions=True,
        )
        assert sum(isinstance(item, NavigationToken) for item in results) == 1
        assert sum(isinstance(item, StaleView) for item in results) == 1
    finally:
        await client.aclose()


async def test_process_exit_after_partial_render_recovers_without_resend(
    nav_redis_client, nav_redis_url
):
    import os
    import sys

    prefix = f"test:nav:{uuid4().hex}"
    script = """
import asyncio, os, sys
from redis.asyncio import Redis
from aiogram_nav.errors import RenderUnknown
from aiogram_nav.storage.redis import RedisNavigationRepository
from tests.test_redis_recovery import navigation
from tests.test_redis_backend import KEY
from tests.test_nav_recovery import StagedPresenter
async def main():
    client = Redis.from_url(sys.argv[1])
    repo = RedisNavigationRepository(redis=client, prefix=sys.argv[2])
    await repo.initialize()
    nav = navigation(repo, StagedPresenter())
    try:
        await nav.for_conversation(KEY).go("main", operation_id="crashed-render")
    except RenderUnknown:
        os._exit(23)
    os._exit(24)
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        nav_redis_url,
        prefix,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ},
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 15)
        assert process.returncode == 23, (stdout.decode(), stderr.decode())
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    repo = await repository(nav_redis_client, prefix)
    presenter = StagedPresenter()
    presenter.interrupt = False
    nav = navigation(repo, presenter)
    await nav.recover(KEY, operation_id="crashed-render")
    assert presenter.sends == 0
    assert (await repo.load(KEY)).snapshot.view.messages[0].message_id == 99


async def test_commit_response_loss_reconnect_lookup_and_retry(nav_redis_client):
    import hashlib

    from aiogram_nav.errors import CommitUnknown
    from aiogram_nav.models import NavigationMutation
    from aiogram_nav.storage.redis_scripts import COMMIT

    sha = hashlib.sha1(COMMIT.encode(), usedforsecurity=False).hexdigest()

    class Unreliable:
        armed = False
        offline = False

        async def execute_command(self, *args):
            if self.offline:
                raise ConnectionError("connection unavailable")
            result = await nav_redis_client.execute_command(*args)
            if self.armed and args[0] == "EVALSHA" and args[1] == sha:
                self.armed = False
                raise ConnectionError("commit response lost")
            return result

    client = Unreliable()
    repo = await repository(client)
    prepared, first = await enter(repo)
    mutation = NavigationMutation("uncertain-touch", prepared.session_id, kind="touch")
    client.armed = True
    with pytest.raises(CommitUnknown):
        await repo.commit(KEY, expected_version=first.version, mutation=mutation)
    client.offline = True
    with pytest.raises(PersistenceUnavailable):
        await repo.load(KEY)
    client.offline = False
    status = await repo.lookup_operation(KEY, operation_id="uncertain-touch")
    assert status.status == "completed"
    retried = await repo.commit(KEY, expected_version=first.version, mutation=mutation)
    assert retried.duplicate and retried.snapshot.activity_revision == 2


async def test_script_cache_flush_recovers_without_discarding_evidence(nav_redis_client):
    repo = await repository(nav_redis_client)
    _, first = await enter(repo)
    # This fixture must point at a dedicated disposable Redis server.
    await nav_redis_client.script_flush()
    _, second = await enter(repo, "panel", "after-script-flush")
    assert second.snapshot.session_id == first.snapshot.session_id
    assert second.snapshot.nav_revision == 2
