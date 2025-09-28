"""Performance sanity tests for memory backend hot paths."""

import asyncio
import time
from unittest.mock import patch

import pytest

from aiogram_sentinel.storage.memory import (
    MemoryBlocklist,
    MemoryDebounce,
    MemoryRateLimiter,
    MemoryUserRepo,
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
        assert duration < performance_thresholds["rate_limit_increment"]

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
        for _ in range(10):
            await limiter.allow(key, 10, window)

        # Measure single get
        start_time = time.time()
        count = await limiter.get_remaining(key, 10, window)
        end_time = time.time()

        duration = end_time - start_time
        assert duration < performance_thresholds["rate_limit_increment"]
        assert count == 10

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
        assert duration < performance_thresholds["debounce_check"]
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
    async def test_blocklist_check_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test blocklist check performance."""
        blocklist = MemoryBlocklist()
        user_id = 12345

        # Measure single check
        start_time = time.time()
        is_blocked = await blocklist.is_blocked(user_id)
        end_time = time.time()

        duration = end_time - start_time
        assert duration < performance_thresholds["blocklist_check"]
        assert is_blocked is False

        # Block user
        await blocklist.set_blocked(user_id, True)

        # Measure multiple checks
        start_time = time.time()
        for _ in range(100):
            await blocklist.is_blocked(user_id)
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["blocklist_check"]

    @pytest.mark.asyncio
    async def test_blocklist_operations_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test blocklist operations performance."""
        blocklist = MemoryBlocklist()

        # Measure block operations
        start_time = time.time()
        for i in range(100):
            await blocklist.set_blocked(i, True)
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["blocklist_check"]

        # Measure unblock operations
        start_time = time.time()
        for i in range(100):
            await blocklist.set_blocked(i, False)
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["blocklist_check"]

    @pytest.mark.asyncio
    async def test_user_repo_operations_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test user repository operations performance."""
        user_repo = MemoryUserRepo()

        # Measure registration operations
        start_time = time.time()
        for i in range(100):
            await user_repo.register_user(i, username=f"user{i}")
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["user_repo_operation"]

        # Measure get operations
        start_time = time.time()
        for i in range(100):
            await user_repo.get_user(i)
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["user_repo_operation"]

        # Measure is_registered operations
        start_time = time.time()
        for i in range(100):
            await user_repo.is_registered(i)
        end_time = time.time()

        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["user_repo_operation"]

    @pytest.mark.asyncio
    async def test_concurrent_operations_performance(
        self, performance_thresholds: dict[str, float]
    ) -> None:
        """Test concurrent operations performance."""
        limiter = MemoryRateLimiter()
        debounce = MemoryDebounce()
        blocklist = MemoryBlocklist()
        user_repo = MemoryUserRepo()

        # Test concurrent rate limiter operations
        async def rate_limiter_ops() -> None:
            for i in range(50):
                await limiter.allow(f"user:{i}:handler", 10, 60)

        # Test concurrent debounce operations
        async def debounce_ops() -> None:
            for i in range(50):
                await debounce.seen(f"user:{i}:handler", 5, "fingerprint")

        # Test concurrent blocklist operations
        async def blocklist_ops() -> None:
            for i in range(50):
                await blocklist.set_blocked(i, True)

        # Test concurrent user repo operations
        async def user_repo_ops() -> None:
            for i in range(50):
                await user_repo.register_user(i, username=f"user{i}")

        # Run all operations concurrently
        start_time = time.time()
        await asyncio.gather(
            rate_limiter_ops(),
            debounce_ops(),
            blocklist_ops(),
            user_repo_ops(),
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
        blocklist = MemoryBlocklist()

        # Test with large number of users
        num_users = 1000

        # Add many users to blocklist
        start_time = time.time()
        for i in range(num_users):
            await blocklist.set_blocked(i, True)
        end_time = time.time()

        avg_duration = (end_time - start_time) / num_users
        assert avg_duration < performance_thresholds["blocklist_check"]

        # Check many users
        start_time = time.time()
        for i in range(num_users):
            await blocklist.is_blocked(i)
        end_time = time.time()

        avg_duration = (end_time - start_time) / num_users
        assert avg_duration < performance_thresholds["blocklist_check"]

        # Add many rate limit entries
        start_time = time.time()
        for i in range(num_users):
            await limiter.allow(f"user:{i}:handler", 10, 60)
        end_time = time.time()

        avg_duration = (end_time - start_time) / num_users
        assert avg_duration < performance_thresholds["rate_limit_increment"]

    @pytest.mark.asyncio
    async def test_memory_usage_scalability(self) -> None:
        """Test memory usage scalability."""
        limiter = MemoryRateLimiter()
        blocklist = MemoryBlocklist()

        # Add many entries
        num_entries = 10000

        # Add to rate limiter
        for i in range(num_entries):
            await limiter.allow(f"user:{i}:handler", 10, 60)

        # Add to blocklist
        for i in range(num_entries):
            await blocklist.set_blocked(i, True)

        # Operations should still be fast
        start_time = time.time()
        for i in range(100):
            await limiter.get_remaining(f"user:{i}:handler", 10, 60)
            await blocklist.is_blocked(i)
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
        blocklist = MemoryBlocklist()
        user_repo = MemoryUserRepo()

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

        # Blocklist edge cases
        edge_user_ids = [0, -1, 999999999999]

        for user_id in edge_user_ids:
            start_time = time.time()
            await blocklist.set_blocked(user_id, True)
            await blocklist.is_blocked(user_id)
            await blocklist.set_blocked(user_id, False)
            end_time = time.time()

            duration = end_time - start_time
            assert duration < performance_thresholds["blocklist_check"]

        # User repo edge cases
        for user_id in edge_user_ids:
            start_time = time.time()
            await user_repo.register_user(user_id, username="")
            await user_repo.is_registered(user_id)
            await user_repo.get_user(user_id)
            end_time = time.time()

            duration = end_time - start_time
            assert duration < performance_thresholds["user_repo_operation"]
