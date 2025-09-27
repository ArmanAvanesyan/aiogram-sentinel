"""Unit tests for MemoryRateLimiter."""

import asyncio
import pytest
from unittest.mock import patch

from aiogram_sentinel.storage.memory import MemoryRateLimiter


@pytest.mark.unit
class TestMemoryRateLimiter:
    """Test MemoryRateLimiter functionality."""

    @pytest.mark.asyncio
    async def test_increment_rate_limit(self, rate_limiter, mock_time):
        """Test rate limit increment."""
        key = "user:123:handler"
        window = 60
        
        count = await rate_limiter.increment_rate_limit(key, window)
        assert count == 1
        
        count = await rate_limiter.increment_rate_limit(key, window)
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_rate_limit(self, rate_limiter, mock_time):
        """Test getting current rate limit count."""
        key = "user:123:handler"
        window = 60
        
        # Initially should be 0
        count = await rate_limiter.get_rate_limit(key)
        assert count == 0
        
        # After increment
        await rate_limiter.increment_rate_limit(key, window)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 1

    @pytest.mark.asyncio
    async def test_reset_rate_limit(self, rate_limiter, mock_time):
        """Test rate limit reset."""
        key = "user:123:handler"
        window = 60
        
        # Increment first
        await rate_limiter.increment_rate_limit(key, window)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 1
        
        # Reset
        await rate_limiter.reset_rate_limit(key)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 0

    @pytest.mark.asyncio
    async def test_window_expiration(self, rate_limiter, mock_time_advance):
        """Test rate limit window expiration."""
        key = "user:123:handler"
        window = 60
        
        # Add some requests
        await rate_limiter.increment_rate_limit(key, window)
        await rate_limiter.increment_rate_limit(key, window)
        
        count = await rate_limiter.get_rate_limit(key)
        assert count == 2
        
        # Advance time beyond window
        mock_time_advance.advance(61)
        
        # Should have 0 requests (window expired)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 0

    @pytest.mark.asyncio
    async def test_multiple_keys(self, rate_limiter, mock_time):
        """Test rate limiting with multiple keys."""
        key1 = "user:123:handler1"
        key2 = "user:123:handler2"
        window = 60
        
        # Increment different keys
        count1 = await rate_limiter.increment_rate_limit(key1, window)
        count2 = await rate_limiter.increment_rate_limit(key2, window)
        
        assert count1 == 1
        assert count2 == 1
        
        # Check individual counts
        assert await rate_limiter.get_rate_limit(key1) == 1
        assert await rate_limiter.get_rate_limit(key2) == 1

    @pytest.mark.asyncio
    async def test_sliding_window_behavior(self, rate_limiter, mock_time_advance):
        """Test sliding window behavior."""
        key = "user:123:handler"
        window = 10
        
        # Add requests at different times
        await rate_limiter.increment_rate_limit(key, window)
        mock_time_advance.advance(5)
        
        await rate_limiter.increment_rate_limit(key, window)
        mock_time_advance.advance(5)
        
        await rate_limiter.increment_rate_limit(key, window)
        
        # Should have 3 requests
        count = await rate_limiter.get_rate_limit(key)
        assert count == 3
        
        # Advance time to expire first request (60 second window)
        mock_time_advance.advance(61)
        
        # Should have 0 requests (all expired)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 0

    @pytest.mark.asyncio
    async def test_concurrent_increments(self, rate_limiter, mock_time):
        """Test concurrent rate limit increments."""
        key = "user:123:handler"
        window = 60
        
        # Simulate concurrent increments
        tasks = []
        for _ in range(10):
            task = rate_limiter.increment_rate_limit(key, window)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # All should return sequential counts (1, 2, 3, ..., 10)
        expected_counts = list(range(1, 11))
        assert results == expected_counts
        
        # Final count should be 10
        count = await rate_limiter.get_rate_limit(key)
        assert count == 10

    @pytest.mark.asyncio
    async def test_edge_case_empty_key(self, rate_limiter, mock_time):
        """Test edge case with empty key."""
        key = ""
        window = 60
        
        count = await rate_limiter.increment_rate_limit(key, window)
        assert count == 1
        
        count = await rate_limiter.get_rate_limit(key)
        assert count == 1

    @pytest.mark.asyncio
    async def test_edge_case_zero_window(self, rate_limiter, mock_time):
        """Test edge case with zero window."""
        key = "user:123:handler"
        window = 0
        
        count = await rate_limiter.increment_rate_limit(key, window)
        assert count == 1
        
        # With zero window, should still have 1 (implementation doesn't auto-expire)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 1

    @pytest.mark.asyncio
    async def test_edge_case_negative_window(self, rate_limiter, mock_time):
        """Test edge case with negative window."""
        key = "user:123:handler"
        window = -1
        
        count = await rate_limiter.increment_rate_limit(key, window)
        assert count == 1
        
        # With negative window, should still have 1 (implementation doesn't auto-expire)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 1

    @pytest.mark.asyncio
    async def test_memory_cleanup(self, rate_limiter, mock_time_advance):
        """Test memory cleanup of expired entries."""
        key = "user:123:handler"
        window = 10
        
        # Add request
        await rate_limiter.increment_rate_limit(key, window)
        
        # Advance time beyond 60 second window
        mock_time_advance.advance(61)
        
        # Get count (should trigger cleanup)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 0
        
        # Internal storage should be cleaned up (empty deque)
        assert len(rate_limiter._counters[key]) == 0

    @pytest.mark.asyncio
    async def test_reset_nonexistent_key(self, rate_limiter, mock_time):
        """Test resetting a non-existent key."""
        key = "nonexistent:key"
        
        # Should not raise an error
        await rate_limiter.reset_rate_limit(key)
        
        # Count should still be 0
        count = await rate_limiter.get_rate_limit(key)
        assert count == 0
