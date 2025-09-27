"""Unit tests for MemoryDebounce."""

import asyncio
import pytest
from unittest.mock import patch

from aiogram_sentinel.storage.memory import MemoryDebounce


@pytest.mark.unit
class TestMemoryDebounce:
    """Test MemoryDebounce functionality."""

    @pytest.mark.asyncio
    async def test_is_debounced_false(self, debounce, mock_time):
        """Test is_debounced returns False for new key."""
        key = "user:123:handler"
        
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is False

    @pytest.mark.asyncio
    async def test_set_debounce(self, debounce, mock_time):
        """Test setting debounce."""
        key = "user:123:handler"
        delay = 5.0
        
        await debounce.set_debounce(key, delay)
        
        # Should be debounced immediately after setting
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is True

    @pytest.mark.asyncio
    async def test_debounce_expiration(self, debounce, mock_time_advance):
        """Test debounce expiration after delay."""
        key = "user:123:handler"
        delay = 5.0
        
        # Set debounce
        await debounce.set_debounce(key, delay)
        
        # Should be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is True
        
        # Advance time beyond delay
        mock_time_advance.advance(6.0)
        
        # Should no longer be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is False

    @pytest.mark.asyncio
    async def test_debounce_boundary(self, debounce, mock_time_advance):
        """Test debounce at exact boundary."""
        key = "user:123:handler"
        delay = 5.0
        
        # Set debounce
        await debounce.set_debounce(key, delay)
        
        # Advance time to exactly the delay
        mock_time_advance.advance(5.0)
        
        # Should still be debounced (boundary case)
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is True
        
        # Advance time slightly beyond delay
        mock_time_advance.advance(0.1)
        
        # Should no longer be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is False

    @pytest.mark.asyncio
    async def test_multiple_keys(self, debounce, mock_time):
        """Test debouncing with multiple keys."""
        key1 = "user:123:handler1"
        key2 = "user:123:handler2"
        delay = 5.0
        
        # Set debounce for different keys
        await debounce.set_debounce(key1, delay)
        await debounce.set_debounce(key2, delay)
        
        # Both should be debounced
        assert await debounce.is_debounced(key1) is True
        assert await debounce.is_debounced(key2) is True

    @pytest.mark.asyncio
    async def test_debounce_override(self, debounce, mock_time_advance):
        """Test overriding existing debounce."""
        key = "user:123:handler"
        delay1 = 5.0
        delay2 = 10.0
        
        # Set initial debounce
        await debounce.set_debounce(key, delay1)
        
        # Advance time
        mock_time_advance.advance(3.0)
        
        # Override with longer delay
        await debounce.set_debounce(key, delay2)
        
        # Advance time beyond first delay but within second
        mock_time_advance.advance(3.0)  # Total: 6.0, second delay: 10.0
        
        # Should still be debounced (overridden)
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is True
        
        # Advance time beyond second delay
        mock_time_advance.advance(5.0)  # Total: 11.0
        
        # Should no longer be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is False

    @pytest.mark.asyncio
    async def test_edge_case_zero_delay(self, debounce, mock_time):
        """Test edge case with zero delay."""
        key = "user:123:handler"
        delay = 0.0
        
        # Set debounce with zero delay
        await debounce.set_debounce(key, delay)
        
        # Should immediately not be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is False

    @pytest.mark.asyncio
    async def test_edge_case_negative_delay(self, debounce, mock_time):
        """Test edge case with negative delay."""
        key = "user:123:handler"
        delay = -1.0
        
        # Set debounce with negative delay
        await debounce.set_debounce(key, delay)
        
        # Should immediately not be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is False

    @pytest.mark.asyncio
    async def test_edge_case_empty_key(self, debounce, mock_time):
        """Test edge case with empty key."""
        key = ""
        delay = 5.0
        
        # Set debounce with empty key
        await debounce.set_debounce(key, delay)
        
        # Should be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is True

    @pytest.mark.asyncio
    async def test_memory_cleanup(self, debounce, mock_time_advance):
        """Test memory cleanup of expired entries."""
        key = "user:123:handler"
        delay = 5.0
        
        # Set debounce
        await debounce.set_debounce(key, delay)
        
        # Advance time beyond delay
        mock_time_advance.advance(6.0)
        
        # Check debounce (should trigger cleanup)
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is False
        
        # Internal storage should be cleaned up
        assert key not in debounce._debounces

    @pytest.mark.asyncio
    async def test_concurrent_debounce_operations(self, debounce, mock_time):
        """Test concurrent debounce operations."""
        key = "user:123:handler"
        delay = 5.0
        
        # Simulate concurrent operations
        tasks = []
        for _ in range(5):
            task = debounce.set_debounce(key, delay)
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Should be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is True

    @pytest.mark.asyncio
    async def test_debounce_precision(self, debounce, mock_time_advance):
        """Test debounce timing precision."""
        key = "user:123:handler"
        delay = 0.1  # 100ms
        
        # Set debounce
        await debounce.set_debounce(key, delay)
        
        # Should be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is True
        
        # Advance time slightly less than delay
        mock_time_advance.advance(0.05)  # 50ms
        
        # Should still be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is True
        
        # Advance time slightly more than delay
        mock_time_advance.advance(0.06)  # Total: 110ms
        
        # Should no longer be debounced
        is_debounced = await debounce.is_debounced(key)
        assert is_debounced is False

    @pytest.mark.asyncio
    async def test_debounce_with_different_delays(self, debounce, mock_time_advance):
        """Test debouncing with different delay values."""
        key1 = "user:123:handler1"
        key2 = "user:123:handler2"
        key3 = "user:123:handler3"
        
        # Set different delays
        await debounce.set_debounce(key1, 1.0)
        await debounce.set_debounce(key2, 5.0)
        await debounce.set_debounce(key3, 10.0)
        
        # All should be debounced
        assert await debounce.is_debounced(key1) is True
        assert await debounce.is_debounced(key2) is True
        assert await debounce.is_debounced(key3) is True
        
        # Advance time to expire first
        mock_time_advance.advance(1.1)
        
        # First should be expired, others still debounced
        assert await debounce.is_debounced(key1) is False
        assert await debounce.is_debounced(key2) is True
        assert await debounce.is_debounced(key3) is True
        
        # Advance time to expire second
        mock_time_advance.advance(4.0)  # Total: 5.1
        
        # First two should be expired, third still debounced
        assert await debounce.is_debounced(key1) is False
        assert await debounce.is_debounced(key2) is False
        assert await debounce.is_debounced(key3) is True
        
        # Advance time to expire third
        mock_time_advance.advance(5.0)  # Total: 10.1
        
        # All should be expired
        assert await debounce.is_debounced(key1) is False
        assert await debounce.is_debounced(key2) is False
        assert await debounce.is_debounced(key3) is False
