"""Explicit native selection is validated before backend namespace side effects."""

from types import SimpleNamespace

import pytest

from aiogram_idle import IdleConfig, MemoryIdleBackend
from aiogram_idle.engines import native_core
from aiogram_idle.errors import ConfigurationError
from aiogram_idle.storage.redis import RedisIdleBackend


@pytest.mark.parametrize("backend", ["memory", "redis"])
@pytest.mark.parametrize("failure", [ImportError("missing"), OSError("wrong platform")])
def test_native_loader_failure_precedes_backend_creation(monkeypatch, backend, failure):
    native_core.cache_clear()

    def broken(_):
        raise failure

    monkeypatch.setattr("aiogram_idle.engines.importlib.import_module", broken)
    with pytest.raises(ConfigurationError):
        if backend == "memory":
            MemoryIdleBackend(config=IdleConfig(engine="rust"), storage_format=3)
        else:
            RedisIdleBackend(redis=object(), config=IdleConfig(engine="rust"), storage_format=3)
    native_core.cache_clear()


@pytest.mark.parametrize("abi", [True, 2])
def test_native_skew_precedes_redis_client_inspection(monkeypatch, abi):
    native_core.cache_clear()
    monkeypatch.setattr(
        "aiogram_idle.engines.importlib.import_module",
        lambda _: SimpleNamespace(API_VERSION=abi, ENGINE_VERSION="0.3.1"),
    )
    with pytest.raises(ConfigurationError):
        RedisIdleBackend(redis=object(), config=IdleConfig(engine="rust"), storage_format=3)
    native_core.cache_clear()
