"""Correctness patch preserves generations, replay promises and fresh observations."""

from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import pytest

from aiogram_idle import IdleConfig, IdleRuntime, MemoryIdleBackend
from aiogram_idle.clock import ManualClock
from aiogram_idle.errors import ConfigurationMismatch, Overloaded
from aiogram_idle.storage.receipts import Receipts
from aiogram_idle.storage.redis import RedisIdleBackend
from aiogram_idle.storage.redis_transport import RedisClock


@pytest.mark.parametrize(
    "field",
    [
        "recovery_retention_seconds",
        "max_conversations",
        "max_receipts_per_conversation",
        "max_tokens_per_conversation",
        "max_params_bytes",
        "max_components_bytes",
    ],
)
def test_runtime_storage_settings_must_match_backend(field):
    from aiogram_idle import IdlePolicies, PromptPolicy
    from tests.runtime_helpers import Adapter, Presenter

    config = IdleConfig()
    backend = MemoryIdleBackend(config=config)
    with pytest.raises(ConfigurationMismatch, match=field):
        IdleRuntime(
            backend=backend,
            config=replace(
                config,
                **{
                    field: getattr(config, field) - 1
                    if field == "max_components_bytes"
                    else getattr(config, field) + 1
                },
            ),
            policies=IdlePolicies({"draft": PromptPolicy()}),
            adapters={"draft": Adapter()},
            presenter=Presenter(backend.clock),
        )
    IdleRuntime(
        backend=backend,
        config=replace(config, poll_seconds=1),
        policies=IdlePolicies({"draft": PromptPolicy()}),
        adapters={"draft": Adapter()},
        presenter=Presenter(backend.clock),
    )


def test_receipt_pruning_is_lazy_and_never_evicts_promised_replay():
    clock = ManualClock(100)
    receipts = Receipts(limit=1, retention=10)
    receipts.save("key", "first", "digest", "original", now=clock.now())
    clock.advance(9)
    with pytest.raises(Overloaded) as captured:
        receipts.prepare("key", "second", "other", now=clock.now())
    assert captured.value.reason == "replay_slots"
    assert captured.value.earliest_safe_expiry == 110
    assert receipts.prepare("key", "first", "digest", now=clock.now()) == "original"
    clock.advance(1)
    assert len(receipts.items["key"]) == 1  # advance alone does not perform maintenance
    assert receipts.prepare("key", "second", "other", now=clock.now()) is None
    assert receipts.items["key"] == {}


def test_clock_sampling_diagnostics_distinguish_interpolation_and_jump():
    clock = RedisClock()
    with patch("aiogram_idle.storage.redis_transport.time.monotonic", return_value=10):
        assert clock.diagnostics()["sample_age_seconds"] is None
        clock.update(100)
    with patch("aiogram_idle.storage.redis_transport.time.monotonic", return_value=12):
        assert clock.now() == 102
        assert clock.diagnostics() == {
            "sample_count": 1,
            "sample_age_seconds": 2,
            "last_jump_seconds": None,
        }
        clock.update(110)
        assert clock.diagnostics()["last_jump_seconds"] == 8
        assert clock.diagnostics()["sample_count"] == 2


async def test_warm_redis_read_fuses_history_time_and_park_check(redis_client):
    class Counted:
        def __init__(self):
            self.commands = []

        async def execute_command(self, *args):
            self.commands.append(args)
            return await redis_client.execute_command(*args)

    client = Counted()
    backend = RedisIdleBackend(redis=client, prefix="test:021:" + uuid4().hex)
    await backend.initialize()
    from aiogram_idle import IdleConversationKey

    key = IdleConversationKey("test", 1, 42, 42)
    await backend.load(key)  # warm script cache
    client.commands.clear()
    before = backend._store.clock.sample_count
    assert await backend.load(key) is None
    assert [item[0] for item in client.commands] == ["EVALSHA"]
    assert backend._store.clock.sample_count == before + 1
    await redis_client.hset(backend._store.prefix + ":parked", backend._store.member(key), "reason")
    from aiogram_idle.errors import BackendInconsistent

    with pytest.raises(BackendInconsistent):
        await backend.load(key)


async def test_real_time_receipt_expiry_is_pruned_only_at_admission(redis_client):
    import asyncio

    from aiogram_idle import IdleConversationKey

    backend = RedisIdleBackend(
        redis=redis_client,
        prefix="test:021:expiry:" + uuid4().hex,
        config=IdleConfig(recovery_retention_seconds=0.08, max_receipts_per_conversation=1),
    )
    key = IdleConversationKey("test", 1, 42, 42)
    session = await backend.open_session(key, lifetime_seconds=30, operation_id="first")
    assert await backend.open_session(key, lifetime_seconds=30, operation_id="first") == session
    with pytest.raises(Overloaded) as error:
        await backend.replace_session(
            key, expected=session.guard, lifetime_seconds=30, operation_id="next"
        )
    assert error.value.reason == "replay_slots"
    await asyncio.sleep(0.1)
    replaced = await backend.replace_session(
        key, expected=session.guard, lifetime_seconds=30, operation_id="next"
    )
    assert replaced.session_id != session.session_id
    engine, _, _ = await backend._store.read(key)
    receipts = engine._receipts.items[key]
    assert set(receipts) == {"next"}
    assert receipts["next"].expires_at > backend.clock.now()


def test_overloaded_preserves_exception_constructor_compatibility():
    assert Overloaded().args == ()
    assert Overloaded("a", "b").args == ("a", "b")
