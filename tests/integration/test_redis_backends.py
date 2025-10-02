"""Integration tests for Redis backends."""

import os
from typing import Any

import pytest

from aiogram_sentinel.storage.redis import (
    RedisDebounce,
    RedisRateLimiter,
)


@pytest.mark.integration
@pytest.mark.skip(reason="Redis integration tests require Redis server to be running")
class TestRedisBackends:
    """Integration tests for Redis backends."""

    @pytest.fixture
    def redis_url(self) -> str:
        """Get Redis URL from environment or use default."""
        return os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")

    @pytest.fixture
    async def redis_backends(self, redis_url: str) -> Any:
        """Create Redis backend instances."""
        from redis.asyncio import Redis

        redis_client = Redis.from_url(redis_url)  # type: ignore
        await redis_client.flushdb()  # type: ignore

        backends = {
            "rate_limiter": RedisRateLimiter(redis_client, "test:"),
            "debounce": RedisDebounce(redis_client, "test:"),
        }

        yield backends

        # Cleanup
        await redis_client.flushdb()  # type: ignore
        await redis_client.close()

    @pytest.mark.asyncio
    async def test_redis_rate_limiter_integration(self, redis_backends: Any) -> None:
        """Test Redis rate limiter integration."""
        rate_limiter = redis_backends["rate_limiter"]
        key = "user:123:handler"
        window = 60

        # Test increment
        count = await rate_limiter.increment_rate_limit(key, window)
        assert count == 1

        # Test get
        count = await rate_limiter.get_rate_limit(key)
        assert count == 1

        # Test multiple increments
        for i in range(5):
            count = await rate_limiter.increment_rate_limit(key, window)
            assert count == i + 2

        # Test reset
        await rate_limiter.reset_rate_limit(key)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 0

    @pytest.mark.asyncio
    async def test_redis_debounce_integration(self, redis_backends: Any) -> None:
        """Test Redis debounce integration."""
        debounce = redis_backends["debounce"]
        key = "user:123:handler"
        delay = 5.0

        # Test initial state
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is False

        # Test set debounce
        await debounce.set_debounce(key, delay)
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is True

        # Test with different key
        key2 = "user:456:handler"
        is_debounced = await debounce.is_debounced(key2)
        assert is_debounced is False

    @pytest.mark.asyncio
    async def test_redis_connection_error_handling(self, redis_url: str) -> None:
        """Test Redis connection error handling."""
        from redis.asyncio import Redis

        # Use invalid Redis URL
        invalid_redis = Redis.from_url("redis://localhost:9999/1")  # type: ignore

        try:
            # This should raise a connection error
            await invalid_redis.ping()  # type: ignore
            pytest.fail("Expected connection error")
        except Exception:
            # Expected behavior
            pass
        finally:
            await invalid_redis.close()

    @pytest.mark.asyncio
    async def test_redis_namespacing(self, redis_backends: Any) -> None:
        """Test Redis key namespacing."""
        rate_limiter = redis_backends["rate_limiter"]
        key = "user:123:handler"
        window = 60

        # Add some data
        await rate_limiter.increment_rate_limit(key, window)

        # Check that keys are properly namespaced
        from redis.asyncio import Redis

        redis_url = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")
        redis_client = Redis.from_url(redis_url)  # type: ignore

        keys = await redis_client.keys("test:*")  # type: ignore
        assert len(keys) > 0
        assert all(key.decode().startswith("test:") for key in keys)

        await redis_client.close()

    @pytest.mark.asyncio
    async def test_redis_concurrent_operations(self, redis_backends: Any) -> None:
        """Test Redis concurrent operations."""
        import asyncio

        rate_limiter = redis_backends["rate_limiter"]
        key = "user:123:handler"
        window = 60

        # Run concurrent increments
        tasks: list[Any] = []
        for _i in range(10):
            task = rate_limiter.increment_rate_limit(key, window)
            tasks.append(task)

        results: list[Any] = await asyncio.gather(*tasks)

        # All should return sequential counts
        expected_counts = list(range(1, 11))
        assert results == expected_counts

        # Final count should be 10
        count = await rate_limiter.get_rate_limit(key)
        assert count == 10
