"""Performance benchmarks for aiogram-sentinel."""

import asyncio
from typing import Any

import pytest

from aiogram_sentinel.storage.memory import (
    MemoryBlocklist,
    MemoryDebounce,
    MemoryRateLimiter,
    MemoryUserRepo,
)


@pytest.mark.asyncio
async def test_rate_limiter_performance() -> None:
    """Benchmark rate limiter operations."""
    rate_limiter = MemoryRateLimiter()
    key = "test:user:123"

    # Simple performance test without benchmark fixture
    for _ in range(1000):
        await rate_limiter.allow(key, max_events=10, per_seconds=60)


@pytest.mark.asyncio
async def test_debounce_performance() -> None:
    """Benchmark debounce operations."""
    debounce = MemoryDebounce()
    key = "test:handler"
    fingerprint = "test_fingerprint"

    # Simple performance test without benchmark fixture
    for _ in range(1000):
        await debounce.seen(key, window_seconds=60, fingerprint=fingerprint)


@pytest.mark.asyncio
async def test_blocklist_performance() -> None:
    """Benchmark blocklist operations."""
    blocklist = MemoryBlocklist()
    user_id = 12345

    # Simple performance test without benchmark fixture
    for _ in range(1000):
        await blocklist.is_blocked(user_id)


@pytest.mark.asyncio
async def test_user_repo_performance() -> None:
    """Benchmark user repository operations."""
    user_repo = MemoryUserRepo()
    user_id = 12345

    # Simple performance test without benchmark fixture
    for i in range(1000):
        await user_repo.register_user(user_id + i, username=f"user{i}")


@pytest.mark.asyncio
async def test_concurrent_operations() -> None:
    """Benchmark concurrent operations."""
    rate_limiter = MemoryRateLimiter()
    user_repo = MemoryUserRepo()

    # Simple performance test without benchmark fixture
    tasks: list[Any] = []
    for i in range(100):
        # Mix of operations
        tasks.append(rate_limiter.allow(f"user:{i}", max_events=10, per_seconds=60))
        tasks.append(user_repo.register_user(i, username=f"user{i}"))

    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_memory_usage_under_load() -> None:
    """Benchmark memory usage under high load."""
    rate_limiter = MemoryRateLimiter()

    # Simple performance test without benchmark fixture
    # Create many different keys to test memory efficiency
    for i in range(10000):
        key = f"user:{i}:handler"
        await rate_limiter.allow(key, max_events=5, per_seconds=60)
