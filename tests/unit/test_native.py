"""Generated public-operation parity and explicit native selection failures."""

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aiogram_sentinel import NativeEngineIncompatible, NativeEngineUnavailable
from aiogram_sentinel.native import load_native
from aiogram_sentinel.storage.memory import MemoryDebounce, MemoryRateLimiter


def test_missing_extension_fails_before_mutation():
    with patch("aiogram_sentinel.native.import_module", side_effect=ImportError):
        with pytest.raises(NativeEngineUnavailable):
            MemoryRateLimiter(engine="rust")
        assert MemoryRateLimiter().engine == "python"


@pytest.mark.parametrize(
    "capabilities",
    [
        None,
        ("aiogram-sentinel-native", 2, "1.3.0"),
        ("aiogram-sentinel-native", 1, "1.2.0"),
    ],
)
def test_incompatible_extension(capabilities):
    module = SimpleNamespace(capabilities=lambda: capabilities)
    with patch("aiogram_sentinel.native.import_module", return_value=module):
        with pytest.raises(NativeEngineIncompatible):
            load_native()


@pytest.fixture
def native():
    pytest.importorskip("_aiogram_sentinel_native")


@pytest.mark.asyncio
async def test_generated_operation_parity(native):
    python_rate, rust_rate = MemoryRateLimiter(), MemoryRateLimiter(engine="rust")
    python_debounce, rust_debounce = MemoryDebounce(), MemoryDebounce(engine="rust")
    rng = random.Random(137)
    now = 0.0
    with patch(
        "aiogram_sentinel.storage.memory.time.monotonic", side_effect=lambda: now
    ):
        for _ in range(2000):
            now += rng.choice([0, 0.25, 1, 10, 60])
            key = rng.choice(["hot", "other", "hot:fp", "unicode-հայ"])
            window = rng.choice([1, 2, 10, 60, 10000])
            limit = rng.choice([1, 2, 10])
            method = rng.choice(
                [
                    "allow",
                    "get_remaining",
                    "increment_rate_limit",
                    "get_rate_limit",
                    "reset_rate_limit",
                ]
            )
            arguments = (
                (key, limit, window)
                if method in ("allow", "get_remaining")
                else ((key, window) if method == "increment_rate_limit" else (key,))
            )
            assert await getattr(python_rate, method)(*arguments) == await getattr(
                rust_rate, method
            )(*arguments)
            method = rng.choice(["seen", "set_debounce", "is_debounced"])
            arguments = (
                (key, window, "fp")
                if method == "seen"
                else (
                    (key, rng.choice([-1, 0, 1, 60]))
                    if method == "set_debounce"
                    else (key,)
                )
            )
            assert await getattr(python_debounce, method)(*arguments) == await getattr(
                rust_debounce, method
            )(*arguments)
            assert python_debounce._debounces == rust_debounce._debounces


@pytest.mark.asyncio
async def test_concurrent_limit_and_no_fallback(native):
    limiter = MemoryRateLimiter(engine="rust")
    assert (
        sum(await asyncio.gather(*(limiter.allow("hot", 17, 60) for _ in range(1000))))
        == 17
    )
    assert await limiter.get_remaining("hot", 17, 60) == 0
    failing = SimpleNamespace(
        allow=lambda *args: (_ for _ in ()).throw(RuntimeError("after mutation"))
    )
    limiter._native = failing
    with pytest.raises(RuntimeError, match="after mutation"):
        await limiter.allow("hot", 17, 60)
    assert not limiter._counters


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [0, -1, True, 1.2, "1"])
async def test_validation_order_same(native, bad):
    errors = []
    for engine in ("python", "rust"):
        with pytest.raises(Exception) as error:
            await MemoryRateLimiter(engine=engine).allow("key", bad, 0)
        errors.append((type(error.value), str(error.value)))
    assert errors[0] == errors[1]


def test_key_fast_path_preserves_public_override_and_validation():
    from aiogram_sentinel.scopes import KeyBuilder, KeyParts, Scope

    builder = KeyBuilder("app")
    for identifier in ("17", "հայ", "-100", ""):
        for bucket in (None, "", "feedback"):
            for namespace in ("throttle", ""):
                try:
                    expected = builder.for_update(
                        KeyParts(namespace, Scope.USER, (identifier,)), bucket=bucket
                    )
                except ValueError as error:
                    with pytest.raises(ValueError, match=str(error)):
                        builder.user(namespace, identifier, bucket=bucket)
                else:
                    assert (
                        builder.user(namespace, identifier, bucket=bucket) == expected
                    )
    builder.app, builder.sep = "changed", "|"
    assert builder.user("ns", 17, bucket="b") == "changed|ns|USER|17|b=b"

    class CustomBuilder(KeyBuilder):
        def for_update(self, parts, **kwargs):
            return "custom:" + parts.identifiers[0]

    assert CustomBuilder("app").user("ns", 17) == "custom:17"


def test_factory_selects_native_only_for_memory(native):
    from aiogram_sentinel import SentinelConfig
    from aiogram_sentinel.storage.factory import build_infra

    infra = build_infra(SentinelConfig(engine="rust"))
    assert infra.rate_limiter.engine == "rust"
    assert infra.debounce.engine == "rust"
    with patch("aiogram_sentinel.native.import_module", side_effect=ImportError):
        infra = build_infra(SentinelConfig(backend="redis", engine="rust"))
    assert type(infra.rate_limiter).__name__ == "RedisRateLimiter"


def test_malformed_policy_metadata_still_fails():
    from aiogram_sentinel import SentinelConfig
    from aiogram_sentinel.middlewares.policy_resolver import PolicyResolverMiddleware
    from aiogram_sentinel.policy import PolicyRegistry

    async def handler(event, data):
        pass

    handler.__sentinel_policies__ = None
    resolver = PolicyResolverMiddleware(PolicyRegistry(), SentinelConfig())
    with pytest.raises(TypeError):
        resolver.resolve_configurations_for_testing(handler)


@pytest.mark.asyncio
async def test_surrogate_and_composite_key_parity(native):
    rates = [MemoryRateLimiter(), MemoryRateLimiter(engine="rust")]
    debounces = [MemoryDebounce(), MemoryDebounce(engine="rust")]
    keys = ["\ud800", "\udfff", "prefix\ud800:fp", "\ud800\udfff", "հայ", "a\0b"]
    with patch("aiogram_sentinel.storage.memory.time.monotonic", return_value=100.0):
        for key in keys:
            assert [await rate.allow(key, 1, 60) for rate in rates] == [True, True]
            assert [await rate.allow(key, 1, 60) for rate in rates] == [False, False]
            assert [await rate.get_remaining(key, 1, 60) for rate in rates] == [0, 0]
            for debounce in debounces:
                await debounce.set_debounce(key + ":" + key, 10)
            assert [await debounce.seen(key, 60, key) for debounce in debounces] == [
                True,
                True,
            ]
            assert debounces[0]._debounces == debounces[1]._debounces
            for rate in rates:
                await rate.reset_rate_limit(key)
            assert [await rate.increment_rate_limit(key, 60) for rate in rates] == [
                1,
                1,
            ]
