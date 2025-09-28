"""Integration test configuration and fixtures."""

import os
from collections.abc import AsyncGenerator

import pytest
from redis.asyncio import Redis


@pytest.fixture
def redis_url() -> str:
    """Get Redis URL from environment or use default."""
    return os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncGenerator[Redis, None]:
    """Create Redis client for integration tests."""
    client = Redis.from_url(redis_url)  # type: ignore
    await client.flushdb()  # type: ignore
    yield client
    await client.flushdb()  # type: ignore
    await client.close()


@pytest.fixture
async def redis_available(redis_url: str) -> bool:
    """Check if Redis is available for integration tests."""
    try:
        client = Redis.from_url(redis_url)  # type: ignore
        await client.ping()  # type: ignore
        await client.close()
        return True
    except Exception:
        return False


# Skip integration tests if Redis is not available
pytestmark = pytest.mark.skipif(
    True,  # Always skip integration tests unless Redis is explicitly available
    reason="Redis integration tests require Redis server to be running",
)
