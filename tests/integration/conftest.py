"""Opt-in Redis fixtures; never erase an application database."""

import os
from uuid import uuid4

import pytest


@pytest.fixture
async def redis_backends():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        if os.getenv("REQUIRE_REDIS") == "1":
            pytest.fail("REQUIRE_REDIS=1 requires TEST_REDIS_URL")
        pytest.skip("Set TEST_REDIS_URL to run real Redis tests")
    redis = pytest.importorskip("redis.asyncio")
    from aiogram_sentinel.storage.redis import RedisDebounce, RedisRateLimiter

    client = redis.Redis.from_url(url)
    prefix = f"sentinel-test:{uuid4().hex}:"
    try:
        await client.ping()
        yield {
            "rate_limiter": RedisRateLimiter(client, prefix),
            "debounce": RedisDebounce(client, prefix),
            "client": client,
            "prefix": prefix,
        }
    finally:
        keys = [key async for key in client.scan_iter(match=f"{prefix}*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()
