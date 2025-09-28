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


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_rate_limiter_performance(benchmark: Any) -> None:
    """Benchmark rate limiter operations."""
    rate_limiter = MemoryRateLimiter()
    key = "test:user:123"

    async def benchmark_fn() -> None:
        for _ in range(1000):
            await rate_limiter.allow(key, max_events=10, per_seconds=60)

    await benchmark(benchmark_fn)


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_debounce_performance(benchmark: Any) -> None:
    """Benchmark debounce operations."""
    debounce = MemoryDebounce()
    key = "test:handler"
    fingerprint = "test_fingerprint"

    async def benchmark_fn() -> None:
        for _ in range(1000):
            await debounce.seen(key, window_seconds=60, fingerprint=fingerprint)

    await benchmark(benchmark_fn)


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_blocklist_performance(benchmark: Any) -> None:
    """Benchmark blocklist operations."""
    blocklist = MemoryBlocklist()
    user_id = 12345

    async def benchmark_fn() -> None:
        for _ in range(1000):
            await blocklist.is_blocked(user_id)

    await benchmark(benchmark_fn)


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_user_repo_performance(benchmark: Any) -> None:
    """Benchmark user repository operations."""
    user_repo = MemoryUserRepo()
    user_id = 12345

    async def benchmark_fn() -> None:
        for i in range(1000):
            await user_repo.register_user(user_id + i, username=f"user{i}")

    await benchmark(benchmark_fn)


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_concurrent_operations(benchmark: Any) -> None:
    """Benchmark concurrent operations."""
    rate_limiter = MemoryRateLimiter()
    user_repo = MemoryUserRepo()

    async def benchmark_fn() -> None:
        tasks: list[Any] = []
        for i in range(100):
            # Mix of operations
            tasks.append(rate_limiter.allow(f"user:{i}", max_events=10, per_seconds=60))
            tasks.append(user_repo.register_user(i, username=f"user{i}"))

        await asyncio.gather(*tasks)

    await benchmark(benchmark_fn)


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_memory_usage_under_load(benchmark: Any) -> None:
    """Benchmark memory usage under high load."""
    rate_limiter = MemoryRateLimiter()

    async def benchmark_fn() -> None:
        # Create many different keys to test memory efficiency
        for i in range(10000):
            key = f"user:{i}:handler"
            await rate_limiter.allow(key, max_events=5, per_seconds=60)

    await benchmark(benchmark_fn)
