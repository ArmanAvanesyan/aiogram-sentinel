"""Cross-client lease, crash, delivery and Lua-cache recovery on actual Redis."""

import asyncio
import os
import signal
import sys
from uuid import uuid4

import pytest

from aiogram_idle.config import IdleConfig
from aiogram_idle.errors import OwnershipLost, PersistenceUnavailable
from aiogram_idle.models import Phase
from aiogram_idle.policies import IdlePolicies, PromptPolicy
from aiogram_idle.runtime import IdleRuntime
from aiogram_idle.storage.redis import RedisIdleBackend

from .runtime_helpers import Adapter, Presenter
from .test_redis_backend import make_due, seed


async def create_backend(client, prefix=None, config=None):
    backend = RedisIdleBackend(
        redis=client, prefix=prefix or f"test:idle:{uuid4().hex}", config=config or IdleConfig()
    )
    await backend.initialize()
    return backend


def runtime(backend, adapter, presenter):
    return IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"draft": PromptPolicy(10, 20)}),
        adapters={"form": adapter},
        presenter=presenter,
        namespace="test",
    )


async def test_two_clients_claim_once_and_expired_lease_recovers(redis_client):
    prefix = f"test:idle:{uuid4().hex}"
    first = await create_backend(redis_client, prefix)
    second = await create_backend(redis_client, prefix)
    key, _, _ = await seed(first)
    await make_due(first, key)
    left, right = await asyncio.gather(
        first.claim_due(limit=1, lease_seconds=0.05),
        second.claim_due(limit=1, lease_seconds=0.05),
    )
    assert len(left) + len(right) == 1
    old = (left or right)[0]
    await asyncio.sleep(0.08)
    fresh = await second.claim_due(limit=1, lease_seconds=5)
    assert len(fresh) == 1 and fresh[0].token != old.token
    with pytest.raises(OwnershipLost):
        await first.renew_claim(old, lease_seconds=5)
    with pytest.raises(OwnershipLost):
        await first.release_claim(old)
    await second.validate_claim(fresh[0])


async def test_concurrent_runtime_workers_deliver_one_question(redis_client, redis_url):
    config = IdleConfig(enabled=True)
    prefix = f"test:idle:{uuid4().hex}"
    first = await create_backend(redis_client, prefix, config)
    from redis.asyncio import Redis

    independent_client = Redis.from_url(redis_url, decode_responses=True)
    second = await create_backend(independent_client, prefix, config)
    presenter = Presenter(first.clock)
    adapter = Adapter()
    one, two = runtime(first, adapter, presenter), runtime(second, adapter, presenter)
    await one.initialize()
    await two.initialize()
    key, _, _ = await seed(first)
    await make_due(first, key)
    await asyncio.gather(one.run_once(), two.run_once())
    assert len(presenter.questions) == 1
    assert (await first.load(key)).idle.phase == Phase.PROMPTED
    await independent_client.aclose()


async def test_script_flush_recovers_without_losing_state(redis_client):
    backend = await create_backend(redis_client)
    key, _, activity = await seed(backend)
    # SCRIPT FLUSH affects the disposable test server's script cache, never its data.
    await redis_client.script_flush()
    touched = await backend.touch(key, expected=activity.guard, operation_id="after-flush")
    assert touched.activity_revision == 2
    assert (await backend.load(key)).activity == touched


async def test_killed_claiming_process_recovers_from_new_client(redis_client, redis_url):
    prefix = f"test:idle:{uuid4().hex}"
    backend = await create_backend(redis_client, prefix)
    key, _, _ = await seed(backend)
    await make_due(backend, key)
    script = """
import asyncio, sys
from redis.asyncio import Redis
from aiogram_idle.storage.redis import RedisIdleBackend
async def main():
    client = Redis.from_url(sys.argv[1])
    backend = RedisIdleBackend(redis=client, prefix=sys.argv[2])
    await backend.initialize()
    claims = await backend.claim_due(limit=1, lease_seconds=0.1)
    assert len(claims) == 1
    print('CLAIMED', flush=True)
    await asyncio.Event().wait()
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        redis_url,
        prefix,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ},
    )
    try:
        marker = await asyncio.wait_for(process.stdout.readline(), timeout=30)
        if marker != b"CLAIMED\n":
            stderr = await process.stderr.read()
            pytest.fail(f"claiming child failed: {stderr.decode()}")
        process.send_signal(signal.SIGKILL)
        await process.wait()
        await asyncio.sleep(0.15)
        from redis.asyncio import Redis

        client = Redis.from_url(redis_url)
        try:
            replacement = await create_backend(client, prefix)
            recovered = await replacement.claim_due(limit=1, lease_seconds=5)
            assert len(recovered) == 1
            assert recovered[0].key == key
        finally:
            await client.aclose()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def test_unavailable_redis_never_falls_back_to_local_state(redis_client):
    from redis.asyncio import Redis

    client = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.1)
    try:
        backend = RedisIdleBackend(redis=client, prefix=f"test:idle:{uuid4().hex}")
        with pytest.raises(PersistenceUnavailable):
            await backend.initialize()
    finally:
        await client.aclose()


async def test_confirmed_question_survives_new_runtime_without_resend(redis_client, monkeypatch):
    from aiogram_idle.effects import OperationEffects

    prefix = f"test:idle:{uuid4().hex}"
    backend = await create_backend(redis_client, prefix, IdleConfig(enabled=True))
    presenter, adapter = Presenter(backend.clock), Adapter()
    first = runtime(backend, adapter, presenter)
    await first.initialize()
    key, _, _ = await seed(backend)
    await make_due(backend, key)
    checkpoint = OperationEffects.checkpoint

    async def interrupt(self, stage, state, result=None):
        if stage == "question" and state == "confirmed":
            raise asyncio.CancelledError
        await checkpoint(self, stage, state, result)

    monkeypatch.setattr(OperationEffects, "checkpoint", interrupt)
    with pytest.raises(asyncio.CancelledError):
        await first.run_once()
    saved = await backend.load(key)
    assert saved.idle.prompt.messages
    monkeypatch.setattr(OperationEffects, "checkpoint", checkpoint)
    recovered_backend = await create_backend(redis_client, prefix, IdleConfig(enabled=True))
    recovered = runtime(recovered_backend, adapter, presenter)
    await recovered.initialize()
    await recovered.run_once()
    current = await recovered_backend.load(key)
    assert current.idle.phase == Phase.PROMPTED
    assert current.idle.prompt == saved.idle.prompt
    assert len(presenter.questions) == 1


async def test_ambiguous_question_is_not_resent_after_reconstruction(redis_client):
    prefix = f"test:idle:{uuid4().hex}"
    backend = await create_backend(redis_client, prefix, IdleConfig(enabled=True))
    presenter, adapter = Presenter(backend.clock), Adapter()
    presenter.show_errors = [TimeoutError("response lost after send")]
    first = runtime(backend, adapter, presenter)
    await first.initialize()
    key, _, _ = await seed(backend)
    await make_due(backend, key)
    await first.run_once()
    assert (await backend.load(key)).idle.phase == Phase.DELIVERY_UNKNOWN
    recovered_backend = await create_backend(redis_client, prefix, IdleConfig(enabled=True))
    recovered = runtime(recovered_backend, adapter, presenter)
    await recovered.initialize()
    await recovered.reconcile()
    await recovered.run_once()
    assert len(presenter.questions) == 1
    assert (await recovered_backend.load(key)).idle.phase == Phase.DELIVERY_UNKNOWN


async def test_concurrent_answers_have_one_business_winner(redis_client):
    from aiogram_idle.controls import ControlContext

    prefix = f"test:idle:{uuid4().hex}"
    backend = await create_backend(redis_client, prefix, IdleConfig(enabled=True))
    presenter, adapter = Presenter(backend.clock), Adapter()
    first = runtime(backend, adapter, presenter)
    await first.initialize()
    key, _, _ = await seed(backend)
    await make_due(backend, key)
    await first.run_once()
    prompt = await first.current_prompt(key)
    assert prompt is not None
    other_backend = await create_backend(redis_client, prefix, IdleConfig(enabled=True))
    second = runtime(other_backend, adapter, presenter)
    await second.initialize()
    answer = ControlContext(
        key,
        key.user_id,
        transport="commands",
        prompt_id=prompt.prompt_id,
        operation_id="continue-winner",
    )
    cancel = ControlContext(
        key,
        key.user_id,
        transport="commands",
        prompt_id=prompt.prompt_id,
        operation_id="cancel-winner",
    )
    # Both explicit answers compete through the same persisted transition.
    await asyncio.gather(first.continue_current(answer), second.cancel_current(cancel))
    actions = [call for call in adapter.calls if call == "resume" or call.startswith("abandon:")]
    assert len(actions) == 1
    assert len(presenter.finishes) == 1
    assert (await backend.load(key)).idle.phase in {Phase.ACTIVE, Phase.DISARMED}


async def test_lost_commit_response_is_lookupable_and_deduplicated(redis_client):
    import hashlib

    from aiogram_idle.errors import CommitUnknown
    from aiogram_idle.storage.redis_scripts import COMMIT

    commit_sha = hashlib.sha1(COMMIT.encode(), usedforsecurity=False).hexdigest()

    class UnreliableClient:
        lose_response = False
        disconnected = False

        async def execute_command(self, *args):
            if self.disconnected:
                raise ConnectionError("temporary disconnection")
            result = await redis_client.execute_command(*args)
            if self.lose_response and args[0] == "EVALSHA" and args[1] == commit_sha:
                self.lose_response = False
                raise ConnectionError("commit response lost")
            return result

    client = UnreliableClient()
    backend = await create_backend(client)
    key, _, activity = await seed(backend)
    client.lose_response = True
    with pytest.raises(CommitUnknown):
        await backend.touch(
            key, expected=activity.guard, operation_id="uncertain-touch", enabled=True
        )
    client.disconnected = True
    with pytest.raises(PersistenceUnavailable):
        await backend.load(key)
    client.disconnected = False
    lookup = await backend.lookup_operation(key, "uncertain-touch")
    assert lookup.status == "found"
    retried = await backend.touch(
        key, expected=activity.guard, operation_id="uncertain-touch", enabled=True
    )
    assert retried == lookup.result
    assert retried.activity_revision == activity.activity_revision + 1


async def test_continue_competes_with_due_timeout_on_separate_client(redis_client, redis_url):
    from redis.asyncio import Redis

    from aiogram_idle.controls import ControlContext

    prefix = f"test:idle:{uuid4().hex}"
    backend = await create_backend(redis_client, prefix, IdleConfig(enabled=True))
    presenter, adapter = Presenter(backend.clock), Adapter()
    first = runtime(backend, adapter, presenter)
    await first.initialize()
    key, _, _ = await seed(backend)
    await make_due(backend, key)
    await first.run_once()
    prompt = await first.current_prompt(key)
    assert prompt is not None
    # Move only the persisted scheduler deadline to its due boundary, preserving
    # the prompt identity and frozen policy. Neither contender can extend grace.
    await make_due(backend, key)
    client = Redis.from_url(redis_url)
    try:
        second_backend = await create_backend(client, prefix, IdleConfig(enabled=True))
        second = runtime(second_backend, adapter, presenter)
        await second.initialize()
        await asyncio.gather(
            first.continue_current(
                ControlContext(
                    key,
                    key.user_id,
                    transport="commands",
                    prompt_id=prompt.prompt_id,
                    operation_id="late-answer",
                )
            ),
            second.run_once(),
        )
        assert "resume" not in adapter.calls
        assert sum(call.startswith("abandon:") for call in adapter.calls) == 1
        assert len(presenter.finishes) == 1
        assert (await backend.load(key)).idle.phase == Phase.DISARMED
    finally:
        await client.aclose()


async def test_exhausted_preflight_is_persistently_quarantined(redis_client):
    prefix = f"test:idle:{uuid4().hex}"
    config = IdleConfig(enabled=True, retry_max_attempts=1)
    backend = await create_backend(redis_client, prefix, config)
    presenter, adapter = Presenter(backend.clock), Adapter()
    adapter.inspect_errors = [RuntimeError("preflight unavailable")]
    first = runtime(backend, adapter, presenter)
    await first.initialize()
    key, _, _ = await seed(backend)
    await make_due(backend, key)
    await first.run_once()
    record = await backend.load(key)
    assert record.idle.phase == Phase.QUARANTINED
    assert record.idle.operation.attempts == 1
    other = await create_backend(redis_client, prefix, config)
    recovered = runtime(other, adapter, presenter)
    await recovered.initialize()
    await recovered.reconcile()
    await recovered.run_once()
    assert not presenter.questions
    assert (await other.load(key)).idle.phase == Phase.QUARANTINED
