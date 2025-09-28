"""Integration test configuration and fixtures."""

import os

import pytest
from redis.asyncio import Redis


@pytest.fixture
def redis_url():
    """Get Redis URL from environment or use default."""
    return os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")


@pytest.fixture
async def redis_client(redis_url):
    """Create Redis client for integration tests."""
    client = Redis.from_url(redis_url)
    await client.flushdb()  # Clean database before each test
    yield client
    await client.flushdb()  # Clean database after each test
    await client.close()


@pytest.fixture
async def redis_available(redis_url):
    """Check if Redis is available for integration tests."""
    try:
        client = Redis.from_url(redis_url)
        await client.ping()
        await client.close()
        return True
    except Exception:
        return False


# Skip integration tests if Redis is not available
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_REDIS_URL"),
    reason="Redis integration tests require TEST_REDIS_URL environment variable",
)
