"""Format three is explicit for new namespaces and never upgrades old data."""

import json
from unittest.mock import patch
from uuid import uuid4

import pytest

from aiogram_idle import IdleConfig, MemoryIdleBackend
from aiogram_idle.engines import native_core
from aiogram_idle.errors import BackendInconsistent, ConfigurationError, ConfigurationMismatch
from aiogram_idle.storage.redis import RedisIdleBackend


def test_fresh_memory_format3_and_invalid_constructor_inputs():
    assert MemoryIdleBackend(storage_format=3).active_storage_format == 3
    for invalid in [True, 2, 4, "3"]:
        with pytest.raises(ConfigurationError):
            MemoryIdleBackend(storage_format=invalid)


async def test_fresh_redis_marker_is_atomic_and_auto_reopen(redis_client):
    prefix = "test:bootstrap3:" + uuid4().hex
    backend = RedisIdleBackend(redis=redis_client, prefix=prefix, storage_format=3)
    await backend.initialize()
    history = await redis_client.get(prefix + ":created")
    marker = json.loads(await redis_client.get(prefix + ":storage-format"))
    assert marker["format"] == 3 and marker["history"] == history.decode()
    assert await backend.storage_format() == 3
    auto = RedisIdleBackend(redis=redis_client, prefix=prefix)
    await auto.initialize()
    assert auto.active_storage_format == 3
    await redis_client.delete(prefix + ":created")
    with pytest.raises(BackendInconsistent):
        await RedisIdleBackend(redis=redis_client, prefix=prefix, storage_format=3).initialize()


async def test_explicit_format3_rejects_existing_legacy_without_writes(redis_client):
    prefix = "test:bootstrap-old:" + uuid4().hex
    original = RedisIdleBackend(redis=redis_client, prefix=prefix)
    await original.initialize()
    before = await redis_client.get(prefix + ":created")
    with pytest.raises(ConfigurationMismatch, match="migration"):
        await RedisIdleBackend(redis=redis_client, prefix=prefix, storage_format=3).initialize()
    assert await redis_client.get(prefix + ":created") == before
    assert await redis_client.get(prefix + ":storage-format") is None


@pytest.mark.parametrize("error", [ImportError("missing"), OSError("bad architecture")])
def test_native_loader_failure_precedes_any_namespace_mutation(error):
    class Client:
        def __init__(self):
            self.calls = []

        async def execute_command(self, *args):
            self.calls.append(args)

    client = Client()
    native_core.cache_clear()
    try:
        with patch("aiogram_idle.engines.importlib.import_module", side_effect=error):
            with pytest.raises(ConfigurationError):
                RedisIdleBackend(redis=client, config=IdleConfig(engine="rust"), storage_format=3)
        assert client.calls == []
    finally:
        native_core.cache_clear()
