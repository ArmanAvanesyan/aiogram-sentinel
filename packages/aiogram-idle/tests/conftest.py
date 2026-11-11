"""Isolated real-Redis connections; never flush an application database."""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio


@pytest.fixture
def redis_url() -> str:
    value = os.environ.get("AIOGRAM_IDLE_REDIS_URL")
    if value:
        return value
    if os.environ.get("AIOGRAM_IDLE_REQUIRE_REDIS") == "1":
        pytest.fail("AIOGRAM_IDLE_REDIS_URL is required")
    pytest.skip("Set AIOGRAM_IDLE_REDIS_URL to run real-Redis tests")


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[object]:
    redis = pytest.importorskip("redis.asyncio")
    client = redis.Redis.from_url(redis_url, decode_responses=False)
    try:
        await client.ping()
        yield client
    finally:
        await client.aclose()
