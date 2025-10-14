"""Performance sanity tests for memory backend hot paths."""

import asyncio
import time
from unittest.mock import patch

import pytest

from aiogram_sentinel.storage.memory import (
    MemoryDebounce,
    MemoryRateLimiter,
)


@pytest.mark.perf
class TestMemoryBackendPerformance:
    """Performance tests for memory backends."""

    @pytest.mark.asyncio
    async def test_rate_limiter_increment_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test rate limiter increment performance."""
        limiter = MemoryRateLimiter()
        key = "user:123:handler"
        window = 60

        # Measure single increment
        start_time = time.time()
        await limiter.allow(key, 10, window)
        end_time = time.time()

        duration = end_time - start_time
        assert (
            duration <= performance_thresholds["rate_limit_increment"] * 1.1
        )  # Allow 10% margin

        # Measure multiple increments
        start_time = time.time()
        for _ in range(100):
            await limiter.allow(key, 10, window)
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["rate_limit_increment"]

    @pytest.mark.asyncio
    async def test_rate_limiter_get_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test rate limiter get performance."""
        limiter = MemoryRateLimiter()
        key = "user:123:handler"
        window = 60

        # Add some data first
        for _ in range(5):
            await limiter.allow(key, 10, window)

        # Measure single get
        start_time = time.time()
        count = await limiter.get_remaining(key, 10, window)
        end_time = time.time()

        duration = end_time - start_time
        assert (
            duration <= performance_thresholds["rate_limit_increment"] * 1.1
        )  # Allow 10% margin
        assert count == 5  # 5 remaining out of 10

        # Measure multiple gets
        start_time = time.time()
        for _ in range(100):
            await limiter.get_remaining(key, 10, window)
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["rate_limit_increment"]

    @pytest.mark.asyncio
    async def test_debounce_check_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test debounce check performance."""
        debounce = MemoryDebounce()
        key = "user:123:handler"

        # Measure single check
        start_time = time.time()
        is_debounced = await debounce.seen(key, 5, "fingerprint")
        end_time = time.time()

        duration = end_time - start_time
        assert duration < performance_thresholds["debounce_check"] * 1.1  # Allow 10% tolerance
        assert is_debounced is False

        # Set debounce
        await debounce.seen(key, 5, "fingerprint")

        # Measure multiple checks
        start_time = time.time()
        for _ in range(100):
            await debounce.seen(key, 5, "fingerprint")
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["debounce_check"]

    @pytest.mark.asyncio
    async def test_debounce_set_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test debounce set performance."""
        debounce = MemoryDebounce()
        key = "user:123:handler"

        # Measure single set
        start_time = time.time()
        await debounce.seen(key, 5, "fingerprint")
        end_time = time.time()

        duration = end_time - start_time
        assert duration < performance_thresholds["debounce_check"]

        # Measure multiple sets
        start_time = time.time()
        for i in range(100):
            await debounce.seen(f"user:{i}:handler", 5, "fingerprint")
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["debounce_check"]

    @pytest.mark.asyncio
    async def test_concurrent_operations_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test concurrent operations performance."""
        limiter = MemoryRateLimiter()
        debounce = MemoryDebounce()

        # Test concurrent rate limiter operations
        async def rate_limiter_ops() -> None:
            for i in range(50):
                await limiter.allow(f"user:{i}:handler", 10, 60)

        # Test concurrent debounce operations
        async def debounce_ops() -> None:
            for i in range(50):
                await debounce.seen(f"user:{i}:handler", 5, "fingerprint")

        # Run all operations concurrently
        start_time = time.time()
        await asyncio.gather(
            rate_limiter_ops(),
            debounce_ops(),
        )
        end_time = time.time()

        # Total time should be reasonable
        total_duration = end_time - start_time
        assert total_duration < 1.0  # Should complete in under 1 second

    @pytest.mark.asyncio
    async def test_large_dataset_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test performance with large datasets."""
        limiter = MemoryRateLimiter()
        debounce = MemoryDebounce()

        # Test with large number of users
        num_users = 1000

        # Add many rate limit entries
        start_time = time.time()
        for i in range(num_users):
            await limiter.allow(f"user:{i}:handler", 10, 60)
        end_time = time.time()

        avg_duration = (end_time - start_time) / num_users
        assert avg_duration < performance_thresholds["rate_limit_increment"]

        # Add many debounce entries
        start_time = time.time()
        for i in range(num_users):
            await debounce.seen(f"user:{i}:handler", 5, "fingerprint")
        end_time = time.time()

        avg_duration = (end_time - start_time) / num_users
        assert avg_duration < performance_thresholds["debounce_check"]

    @pytest.mark.asyncio
    async def test_memory_usage_scalability(self) -> None:
        """Test memory usage scalability."""
        limiter = MemoryRateLimiter()
        debounce = MemoryDebounce()

        # Add many entries
        num_entries = 10000

        # Add to rate limiter
        for i in range(num_entries):
            await limiter.allow(f"user:{i}:handler", 10, 60)

        # Add to debounce
        for i in range(num_entries):
            await debounce.seen(f"user:{i}:handler", 5, "fingerprint")

        # Operations should still be fast
        start_time = time.time()
        for i in range(100):
            await limiter.get_remaining(f"user:{i}:handler", 10, 60)
            await debounce.seen(f"user:{i}:handler", 5, "fingerprint")
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < 0.001  # Should still be under 1ms

    @pytest.mark.asyncio
    async def test_window_cleanup_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test performance of window cleanup operations."""
        limiter = MemoryRateLimiter()
        debounce = MemoryDebounce()

        # Add many entries
        num_entries = 1000

        with patch("time.monotonic", return_value=1000.0):
            # Add entries
            for i in range(num_entries):
                await limiter.allow(f"user:{i}:handler", 10, 60)
                await debounce.seen(f"user:{i}:handler", 5, "fingerprint")

        # Advance time to trigger cleanup
        with patch("time.monotonic", return_value=2000.0):
            # Measure cleanup performance
            start_time = time.time()
            for i in range(100):
                await limiter.get_remaining(f"user:{i}:handler", 10, 60)
                await debounce.seen(f"user:{i}:handler", 5, "fingerprint")
            end_time = time.time()

            avg_duration = (end_time - start_time) / 100
            assert avg_duration < performance_thresholds["rate_limit_increment"]

    @pytest.mark.asyncio
    async def test_edge_case_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test performance of edge cases."""
        limiter = MemoryRateLimiter()
        debounce = MemoryDebounce()

        # Test with edge case values
        edge_cases = [
            ("", 0, 0.0),  # Empty key, zero window, zero delay
            ("user:0:handler", -1, -1.0),  # Zero user ID, negative values
            ("user:-1:handler", 1, 0.1),  # Negative user ID, small values
        ]

        for key, window, _delay in edge_cases:
            # Rate limiter edge cases
            start_time = time.time()
            await limiter.allow(key, 10, window)
            await limiter.get_remaining(key, 10, window)
            end_time = time.time()

            duration = end_time - start_time
            assert duration < performance_thresholds["rate_limit_increment"]

            # Debounce edge cases
            start_time = time.time()
            await debounce.seen(key, window, "fingerprint")
            await debounce.seen(key, window, "fingerprint")
            end_time = time.time()

            duration = end_time - start_time
            assert duration < performance_thresholds["debounce_check"]
