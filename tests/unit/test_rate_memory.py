"""Unit tests for MemoryRateLimiter."""

import asyncio
from typing import Any
from unittest.mock import Mock

import pytest


@pytest.mark.unit
class TestMemoryRateLimiter:
    """Test MemoryRateLimiter functionality."""

    @pytest.mark.asyncio
    async def test_allow_increment(self, rate_limiter: Any, mock_time: Mock) -> None:
        """Test rate limit allow and increment."""
        key = "user:123:handler"
        max_events = 5
        per_seconds = 60

        # First request should be allowed
        allowed = await rate_limiter.allow(key, max_events, per_seconds)
        assert allowed is True

        # Second request should also be allowed
        allowed = await rate_limiter.allow(key, max_events, per_seconds)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_get_remaining(self, rate_limiter: Any, mock_time: Mock) -> None:
        """Test getting remaining requests."""
        key = "user:123:handler"
        max_events = 5
        per_seconds = 60

        # Initially should be max_events
        remaining = await rate_limiter.get_remaining(key, max_events, per_seconds)
        assert remaining == 5

        # After one request
        await rate_limiter.allow(key, max_events, per_seconds)
        remaining = await rate_limiter.get_remaining(key, max_events, per_seconds)
        assert remaining == 4

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(
        self, rate_limiter: Any, mock_time: Mock
    ) -> None:
        """Test rate limit exceeded behavior."""
        key = "user:123:handler"
        max_events = 2
        per_seconds = 60

        # First two requests should be allowed
        allowed1 = await rate_limiter.allow(key, max_events, per_seconds)
        allowed2 = await rate_limiter.allow(key, max_events, per_seconds)
        assert allowed1 is True
        assert allowed2 is True

        # Third request should be denied
        allowed3 = await rate_limiter.allow(key, max_events, per_seconds)
        assert allowed3 is False

    @pytest.mark.asyncio
    async def test_window_expiration(
        self, rate_limiter: Any, mock_time_advance: Mock
    ) -> None:
        """Test rate limit window expiration."""
        key = "user:123:handler"
        max_events = 2
        per_seconds = 60

        # Use up the limit
        await rate_limiter.allow(key, max_events, per_seconds)
        await rate_limiter.allow(key, max_events, per_seconds)

        # Should be at limit
        remaining = await rate_limiter.get_remaining(key, max_events, per_seconds)
        assert remaining == 0

        # Advance time beyond window
        mock_time_advance.advance(61)
        remaining = await rate_limiter.get_remaining(key, max_events, per_seconds)
        assert remaining == 2

    @pytest.mark.asyncio
    async def test_multiple_keys(self, rate_limiter: Any, mock_time: Mock) -> None:
        """Test rate limiting with multiple keys."""
        key1 = "user:123:handler1"
        key2 = "user:123:handler2"
        max_events = 5
        per_seconds = 60

        # Allow different keys
        allowed1 = await rate_limiter.allow(key1, max_events, per_seconds)
        allowed2 = await rate_limiter.allow(key2, max_events, per_seconds)

        assert allowed1 is True
        assert allowed2 is True

        # Check remaining
        remaining1 = await rate_limiter.get_remaining(key1, max_events, per_seconds)
        remaining2 = await rate_limiter.get_remaining(key2, max_events, per_seconds)

        assert remaining1 == 4
        assert remaining2 == 4

    @pytest.mark.asyncio
    async def test_sliding_window_behavior(
        self, rate_limiter: Any, mock_time_advance: Mock
    ) -> None:
        """Test sliding window behavior."""
        key = "user:123:handler"
        max_events = 5
        per_seconds = 10

        # Add requests at different times
        await rate_limiter.allow(key, max_events, per_seconds)
        mock_time_advance.advance(5)

        await rate_limiter.allow(key, max_events, per_seconds)
        mock_time_advance.advance(5)

        await rate_limiter.allow(key, max_events, per_seconds)

        # Should have 3 requests
        remaining = await rate_limiter.get_remaining(key, max_events, per_seconds)
        assert remaining == 2

        # Advance time to expire first request (10 second window)
        mock_time_advance.advance(11)

        # Should have 0 requests (all expired)
        remaining = await rate_limiter.get_remaining(key, max_events, per_seconds)
        assert remaining == 5

    @pytest.mark.asyncio
    async def test_concurrent_increments(
        self, rate_limiter: Any, mock_time: Mock
    ) -> None:
        """Test concurrent rate limit increments."""
        key = "user:123:handler"
        max_events = 10
        per_seconds = 60

        # Simulate concurrent allow operations
        tasks: list[Any] = []
        for _ in range(10):
            task = rate_limiter.allow(key, max_events, per_seconds)
            tasks.append(task)

        results: list[Any] = await asyncio.gather(*tasks)

        # All should return True
        assert all(result is True for result in results)

        # Final remaining should be 0
        remaining = await rate_limiter.get_remaining(key, max_events, per_seconds)
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_edge_case_empty_key(
        self, rate_limiter: Any, mock_time: Mock
    ) -> None:
        """Test edge case with empty key."""
        key = ""
        max_events = 5
        per_seconds = 60

        allowed = await rate_limiter.allow(key, max_events, per_seconds)
        assert allowed is True

        remaining = await rate_limiter.get_remaining(key, max_events, per_seconds)
        assert remaining == 4

    @pytest.mark.asyncio
    async def test_edge_case_zero_window(
        self, rate_limiter: Any, mock_time: Mock
    ) -> None:
        """Test edge case with zero window."""
        key = "user:123:handler"
        window = 0

        count = await rate_limiter.increment_rate_limit(key, window)
        assert count == 1

        # With zero window, should still have 1 (implementation doesn't auto-expire)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 1

    @pytest.mark.asyncio
    async def test_edge_case_negative_window(
        self, rate_limiter: Any, mock_time: Mock
    ) -> None:
        """Test edge case with negative window."""
        key = "user:123:handler"
        window = -1

        count = await rate_limiter.increment_rate_limit(key, window)
        assert count == 1

        # With negative window, should still have 1 (implementation doesn't auto-expire)
        count = await rate_limiter.get_rate_limit(key)
        assert count == 1

    @pytest.mark.asyncio
    async def test_memory_cleanup(
        self, rate_limiter: Any, mock_time_advance: Mock
    ) -> None:
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
    async def test_reset_nonexistent_key(
        self, rate_limiter: Any, mock_time: Mock
    ) -> None:
        """Test resetting a non-existent key."""
        key = "nonexistent:key"

        # Should not raise an error
        await rate_limiter.reset_rate_limit(key)

        # Count should still be 0
        count = await rate_limiter.get_rate_limit(key)
        assert count == 0
