"""Opt-in real Redis; required CI mode never silently skips infrastructure."""

import importlib
import os

import pytest
import pytest_asyncio


@pytest.fixture
def nav_redis_url():
    url = os.environ.get("AIOGRAM_NAV_REDIS_URL")
    if not url:
        if os.environ.get("AIOGRAM_NAV_REQUIRE_REDIS") == "1":
            pytest.fail("AIOGRAM_NAV_REDIS_URL is required")
        pytest.skip("Set AIOGRAM_NAV_REDIS_URL for real Redis tests")
    return url


@pytest.fixture
def nav_redis_module():
    try:
        return importlib.import_module("redis.asyncio")
    except ImportError:
        if os.environ.get("AIOGRAM_NAV_REQUIRE_REDIS") == "1":
            pytest.fail("Install the redis extra for required real-Redis verification")
        pytest.skip("The redis extra is not installed")


@pytest_asyncio.fixture
async def nav_redis_client(nav_redis_url, nav_redis_module):
    redis = nav_redis_module
    client = redis.Redis.from_url(nav_redis_url, socket_timeout=5, socket_connect_timeout=5)
    await client.ping()
    yield client
    await client.aclose()
