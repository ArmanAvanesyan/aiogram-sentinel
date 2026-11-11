import os

import pytest
import pytest_asyncio


@pytest.fixture
def redis_url():
    value = os.environ.get("AIOGRAM_COORDINATION_REDIS_URL")
    if value:
        return value
    if os.environ.get("AIOGRAM_COORDINATION_REQUIRE_REDIS") == "1":
        pytest.fail("AIOGRAM_COORDINATION_REDIS_URL required")
    pytest.skip("Real Redis URL not configured")


@pytest_asyncio.fixture
async def redis_client(redis_url):
    redis = pytest.importorskip("redis.asyncio")
    client = redis.Redis.from_url(redis_url)
    await client.ping()
    try:
        yield client
    finally:
        await client.aclose()
