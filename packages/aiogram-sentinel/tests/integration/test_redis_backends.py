"""Real Redis tests for the public backend protocols."""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_rate_limit_and_namespace(redis_backends):
    limiter = redis_backends["rate_limiter"]
    assert await limiter.allow("user:123", 2, 60)
    assert await limiter.get_remaining("user:123", 2, 60) == 1
    assert await limiter.allow("user:123", 2, 60)
    assert not await limiter.allow("user:123", 2, 60)
    assert await limiter.get_remaining("user:123", 2, 60) == 0
    client = redis_backends["client"]
    prefix = redis_backends["prefix"]
    keys = [key async for key in client.scan_iter(match=f"{prefix}*")]
    assert keys
    for key in keys:
        assert 0 < await client.ttl(key) <= 60


@pytest.mark.asyncio
async def test_debounce(redis_backends):
    debounce = redis_backends["debounce"]
    assert not await debounce.seen("user", 10, "first")
    assert await debounce.seen("user", 10, "first")
    assert not await debounce.seen("user", 10, "second")


@pytest.mark.asyncio
async def test_concurrent_operations(redis_backends):
    limiter = redis_backends["rate_limiter"]
    results = await asyncio.gather(*(limiter.allow("same", 5, 60) for _ in range(50)))
    assert sum(results) == 5
    debounce = redis_backends["debounce"]
    seen = await asyncio.gather(*(debounce.seen("same", 60, "same") for _ in range(50)))
    assert sum(seen) == 49


@pytest.mark.asyncio
async def test_fixed_expiry_preserved_and_orphan_repaired(redis_backends):
    client = redis_backends["client"]
    prefix = redis_backends["prefix"]
    limiter = redis_backends["rate_limiter"]
    key = f"{prefix}:rate:existing"
    await client.set(key, 1, ex=5)
    assert await limiter.allow("existing", 10, 60)
    assert 0 < await client.ttl(key) <= 5
    key = f"{prefix}:rate:orphan"
    await client.set(key, 1)
    assert await limiter.allow("orphan", 10, 60)
    assert 0 < await client.ttl(key) <= 60
