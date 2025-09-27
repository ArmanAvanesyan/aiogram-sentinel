"""Performance sanity tests for memory backend hot paths."""

import asyncio
import time
import pytest
from unittest.mock import patch

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
    async def test_rate_limiter_increment_performance(self, performance_thresholds):
        """Test rate limiter increment performance."""
        limiter = MemoryRateLimiter()
        key = "user:123:handler"
        window = 60
        
        # Measure single increment
        start_time = time.time()
        await limiter.increment_rate_limit(key, window)
        end_time = time.time()
        
        duration = end_time - start_time
        assert duration < performance_thresholds["rate_limit_increment"]
        
        # Measure multiple increments
        start_time = time.time()
        for _ in range(100):
            await limiter.increment_rate_limit(key, window)
        end_time = time.time()
        
        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["rate_limit_increment"]

    @pytest.mark.asyncio
    async def test_rate_limiter_get_performance(self, performance_thresholds):
        """Test rate limiter get performance."""
        limiter = MemoryRateLimiter()
        key = "user:123:handler"
        window = 60
        
        # Add some data first
        for _ in range(10):
            await limiter.increment_rate_limit(key, window)
        
        # Measure single get
        start_time = time.time()
        count = await limiter.get_rate_limit(key)
        end_time = time.time()
        
        duration = end_time - start_time
        assert duration < performance_thresholds["rate_limit_increment"]
        assert count == 10
        
        # Measure multiple gets
        start_time = time.time()
        for _ in range(100):
            await limiter.get_rate_limit(key)
        end_time = time.time()
        
        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["rate_limit_increment"]

    @pytest.mark.asyncio
    async def test_debounce_check_performance(self, performance_thresholds):
        """Test debounce check performance."""
        debounce = MemoryDebounce()
        key = "user:123:handler"
        delay = 5.0
        
        # Measure single check
        start_time = time.time()
        is_debounced = await debounce.is_debounced(key)
        end_time = time.time()
        
        duration = end_time - start_time
        assert duration < performance_thresholds["debounce_check"]
        assert is_debounced is False
        
        # Set debounce
        await debounce.set_debounce(key, delay)
        
        # Measure multiple checks
        start_time = time.time()
        for _ in range(100):
            await debounce.is_debounced(key)
        end_time = time.time()
        
        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["debounce_check"]

    @pytest.mark.asyncio
    async def test_debounce_set_performance(self, performance_thresholds):
        """Test debounce set performance."""
        debounce = MemoryDebounce()
        key = "user:123:handler"
        delay = 5.0
        
        # Measure single set
        start_time = time.time()
        await debounce.set_debounce(key, delay)
        end_time = time.time()
        
        duration = end_time - start_time
        assert duration < performance_thresholds["debounce_check"]
        
        # Measure multiple sets
        start_time = time.time()
        for i in range(100):
            await debounce.set_debounce(f"user:{i}:handler", delay)
        end_time = time.time()
        
        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["debounce_check"]

    @pytest.mark.asyncio
    async def test_blocklist_check_performance(self, performance_thresholds):
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
        await blocklist.block_user(user_id)
        
        # Measure multiple checks
        start_time = time.time()
        for _ in range(100):
            await blocklist.is_blocked(user_id)
        end_time = time.time()
        
        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["blocklist_check"]

    @pytest.mark.asyncio
    async def test_blocklist_operations_performance(self, performance_thresholds):
        """Test blocklist operations performance."""
        blocklist = MemoryBlocklist()
        
        # Measure block operations
        start_time = time.time()
        for i in range(100):
            await blocklist.block_user(i)
        end_time = time.time()
        
        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["blocklist_check"]
        
        # Measure unblock operations
        start_time = time.time()
        for i in range(100):
            await blocklist.unblock_user(i)
        end_time = time.time()
        
        avg_duration = (end_time - start_time) / 100
        assert avg_duration < performance_thresholds["blocklist_check"]

    @pytest.mark.asyncio
    async def test_user_repo_operations_performance(self, performance_thresholds):
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
    async def test_concurrent_operations_performance(self, performance_thresholds):
        """Test concurrent operations performance."""
        limiter = MemoryRateLimiter()
        debounce = MemoryDebounce()
        blocklist = MemoryBlocklist()
        user_repo = MemoryUserRepo()
        
        # Test concurrent rate limiter operations
        async def rate_limiter_ops():
            for i in range(50):
                await limiter.increment_rate_limit(f"user:{i}:handler", 60)
        
        # Test concurrent debounce operations
        async def debounce_ops():
            for i in range(50):
                await debounce.set_debounce(f"user:{i}:handler", 5.0)
        
        # Test concurrent blocklist operations
        async def blocklist_ops():
            for i in range(50):
                await blocklist.block_user(i)
        
        # Test concurrent user repo operations
        async def user_repo_ops():
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
    async def test_large_dataset_performance(self, performance_thresholds):
        """Test performance with large datasets."""
        limiter = MemoryRateLimiter()
        blocklist = MemoryBlocklist()
        
        # Test with large number of users
        num_users = 1000
        
        # Add many users to blocklist
        start_time = time.time()
        for i in range(num_users):
            await blocklist.block_user(i)
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
            await limiter.increment_rate_limit(f"user:{i}:handler", 60)
        end_time = time.time()
        
        avg_duration = (end_time - start_time) / num_users
        assert avg_duration < performance_thresholds["rate_limit_increment"]

    @pytest.mark.asyncio
    async def test_memory_usage_scalability(self):
        """Test memory usage scalability."""
        limiter = MemoryRateLimiter()
        blocklist = MemoryBlocklist()
        
        # Add many entries
        num_entries = 10000
        
        # Add to rate limiter
        for i in range(num_entries):
            await limiter.increment_rate_limit(f"user:{i}:handler", 60)
        
        # Add to blocklist
        for i in range(num_entries):
            await blocklist.block_user(i)
        
        # Operations should still be fast
        start_time = time.time()
        for i in range(100):
            await limiter.get_rate_limit(f"user:{i}:handler")
            await blocklist.is_blocked(i)
        end_time = time.time()
        
        avg_duration = (end_time - start_time) / 100
        assert avg_duration < 0.001  # Should still be under 1ms

    @pytest.mark.asyncio
    async def test_window_cleanup_performance(self, performance_thresholds):
        """Test performance of window cleanup operations."""
        limiter = MemoryRateLimiter()
        debounce = MemoryDebounce()
        
        # Add many entries
        num_entries = 1000
        
        with patch('time.monotonic', return_value=1000.0):
            # Add entries
            for i in range(num_entries):
                await limiter.increment_rate_limit(f"user:{i}:handler", 60)
                await debounce.set_debounce(f"user:{i}:handler", 5.0)
        
        # Advance time to trigger cleanup
        with patch('time.monotonic', return_value=2000.0):
            # Measure cleanup performance
            start_time = time.time()
            for i in range(100):
                await limiter.get_rate_limit(f"user:{i}:handler")
                await debounce.is_debounced(f"user:{i}:handler")
            end_time = time.time()
            
            avg_duration = (end_time - start_time) / 100
            assert avg_duration < performance_thresholds["rate_limit_increment"]

    @pytest.mark.asyncio
    async def test_edge_case_performance(self, performance_thresholds):
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
        
        for key, window, delay in edge_cases:
            # Rate limiter edge cases
            start_time = time.time()
            await limiter.increment_rate_limit(key, window)
            await limiter.get_rate_limit(key)
            end_time = time.time()
            
            duration = end_time - start_time
            assert duration < performance_thresholds["rate_limit_increment"]
            
            # Debounce edge cases
            start_time = time.time()
            await debounce.set_debounce(key, delay)
            await debounce.is_debounced(key)
            end_time = time.time()
            
            duration = end_time - start_time
            assert duration < performance_thresholds["debounce_check"]
        
        # Blocklist edge cases
        edge_user_ids = [0, -1, 999999999999]
        
        for user_id in edge_user_ids:
            start_time = time.time()
            await blocklist.block_user(user_id)
            await blocklist.is_blocked(user_id)
            await blocklist.unblock_user(user_id)
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
