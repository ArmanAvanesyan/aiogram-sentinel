"""Integration tests for Redis backends."""

import os

import pytest

from aiogram_sentinel.storage.redis import (
    RedisBlocklist,
    RedisDebounce,
    RedisRateLimiter,
    RedisUserRepo,
)


@pytest.mark.integration
class TestRedisBackends:
    """Integration tests for Redis backends."""

    @pytest.fixture
    def redis_url(self):
        """Get Redis URL from environment or use default."""
        return os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")

    @pytest.fixture
    async def redis_backends(self, redis_url):
        """Create Redis backend instances."""
        from redis.asyncio import Redis

        redis_client = Redis.from_url(redis_url)
        await redis_client.flushdb()  # Clean database

        backends = {
            "rate_limiter": RedisRateLimiter(redis_client, "test:"),
            "debounce": RedisDebounce(redis_client, "test:"),
            "blocklist": RedisBlocklist(redis_client, "test:"),
            "user_repo": RedisUserRepo(redis_client, "test:"),
        }

        yield backends

        # Cleanup
        await redis_client.flushdb()
        await redis_client.close()

    @pytest.mark.asyncio
    async def test_redis_rate_limiter_integration(self, redis_backends):
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
    async def test_redis_debounce_integration(self, redis_backends):
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
    async def test_redis_blocklist_integration(self, redis_backends):
        """Test Redis blocklist integration."""
        blocklist = redis_backends["blocklist"]
        user_id = 12345

        # Test initial state
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

        # Test block user
        await blocklist.block_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is True

        # Test unblock user
        await blocklist.unblock_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

    @pytest.mark.asyncio
    async def test_redis_user_repo_integration(self, redis_backends):
        """Test Redis user repository integration."""
        user_repo = redis_backends["user_repo"]
        user_id = 12345

        # Test initial state
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is False

        user_data = await user_repo.get_user(user_id)
        assert user_data is None

        # Test register user
        await user_repo.register_user(user_id, username="testuser", first_name="Test")
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is True

        user_data = await user_repo.get_user(user_id)
        assert user_data is not None
        assert user_data["username"] == "testuser"
        assert user_data["first_name"] == "Test"
        assert "registered_at" in user_data

    @pytest.mark.asyncio
    async def test_redis_connection_error_handling(self, redis_url):
        """Test Redis connection error handling."""
        from redis.asyncio import Redis

        # Use invalid Redis URL
        invalid_redis = Redis.from_url("redis://localhost:9999/1")

        try:
            # This should raise a connection error
            await invalid_redis.ping()
            pytest.fail("Expected connection error")
        except Exception:
            # Expected behavior
            pass
        finally:
            await invalid_redis.close()

    @pytest.mark.asyncio
    async def test_redis_namespacing(self, redis_backends):
        """Test Redis key namespacing."""
        rate_limiter = redis_backends["rate_limiter"]
        key = "user:123:handler"
        window = 60

        # Add some data
        await rate_limiter.increment_rate_limit(key, window)

        # Check that keys are properly namespaced
        from redis.asyncio import Redis

        redis_url = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")
        redis_client = Redis.from_url(redis_url)

        keys = await redis_client.keys("test:*")
        assert len(keys) > 0
        assert all(key.decode().startswith("test:") for key in keys)

        await redis_client.close()

    @pytest.mark.asyncio
    async def test_redis_concurrent_operations(self, redis_backends):
        """Test Redis concurrent operations."""
        import asyncio

        rate_limiter = redis_backends["rate_limiter"]
        key = "user:123:handler"
        window = 60

        # Run concurrent increments
        tasks = []
        for _i in range(10):
            task = rate_limiter.increment_rate_limit(key, window)
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should return sequential counts
        expected_counts = list(range(1, 11))
        assert results == expected_counts

        # Final count should be 10
        count = await rate_limiter.get_rate_limit(key)
        assert count == 10
