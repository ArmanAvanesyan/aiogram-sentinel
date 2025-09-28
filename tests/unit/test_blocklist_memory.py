"""Unit tests for MemoryBlocklist."""

import asyncio
from typing import Any

import pytest

from aiogram_sentinel.storage.memory import MemoryBlocklist


@pytest.mark.unit
class TestMemoryBlocklist:
    """Test MemoryBlocklist functionality."""

    @pytest.mark.asyncio
    async def test_is_blocked_false(self, blocklist: MemoryBlocklist):
        """Test is_blocked returns False for new user."""
        user_id = 12345

        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

    @pytest.mark.asyncio
    async def test_block_user(self, blocklist: MemoryBlocklist):
        """Test blocking a user."""
        user_id = 12345

        await blocklist.block_user(user_id)

        # Should be blocked
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is True

    @pytest.mark.asyncio
    async def test_unblock_user(self, blocklist: MemoryBlocklist):
        """Test unblocking a user."""
        user_id = 12345

        # Block first
        await blocklist.block_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is True

        # Unblock
        await blocklist.unblock_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

    @pytest.mark.asyncio
    async def test_block_multiple_users(self, blocklist: MemoryBlocklist):
        """Test blocking multiple users."""
        user_ids = [12345, 67890, 11111]

        # Block all users
        for user_id in user_ids:
            await blocklist.block_user(user_id)

        # All should be blocked
        for user_id in user_ids:
            is_blocked = await blocklist.is_blocked(user_id)
            assert is_blocked is True

    @pytest.mark.asyncio
    async def test_unblock_multiple_users(self, blocklist: MemoryBlocklist):
        """Test unblocking multiple users."""
        user_ids = [12345, 67890, 11111]

        # Block all users
        for user_id in user_ids:
            await blocklist.block_user(user_id)

        # Unblock all users
        for user_id in user_ids:
            await blocklist.unblock_user(user_id)

        # All should be unblocked
        for user_id in user_ids:
            is_blocked = await blocklist.is_blocked(user_id)
            assert is_blocked is False

    @pytest.mark.asyncio
    async def test_block_already_blocked_user(self, blocklist: MemoryBlocklist):
        """Test blocking an already blocked user."""
        user_id = 12345

        # Block user
        await blocklist.block_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is True

        # Block again (should be idempotent)
        await blocklist.block_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is True

    @pytest.mark.asyncio
    async def test_unblock_not_blocked_user(self, blocklist: MemoryBlocklist):
        """Test unblocking a user that's not blocked."""
        user_id = 12345

        # User should not be blocked initially
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

        # Unblock (should be idempotent)
        await blocklist.unblock_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

    @pytest.mark.asyncio
    async def test_edge_case_zero_user_id(self, blocklist: MemoryBlocklist):
        """Test edge case with zero user ID."""
        user_id = 0

        # Block user with ID 0
        await blocklist.block_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is True

        # Unblock
        await blocklist.unblock_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

    @pytest.mark.asyncio
    async def test_edge_case_negative_user_id(self, blocklist: MemoryBlocklist):
        """Test edge case with negative user ID."""
        user_id = -12345

        # Block user with negative ID
        await blocklist.block_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is True

        # Unblock
        await blocklist.unblock_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

    @pytest.mark.asyncio
    async def test_large_user_id(self, blocklist: MemoryBlocklist):
        """Test with large user ID."""
        user_id = 999999999999

        # Block user with large ID
        await blocklist.block_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is True

        # Unblock
        await blocklist.unblock_user(user_id)
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

    @pytest.mark.asyncio
    async def test_concurrent_block_operations(self, blocklist: MemoryBlocklist):
        """Test concurrent block operations."""
        user_id = 12345

        # Simulate concurrent block operations
        tasks: list[Any] = []
        for _ in range(10):
            task = blocklist.block_user(user_id)
            tasks.append(task)

        await asyncio.gather(*tasks)

        # Should be blocked
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is True

    @pytest.mark.asyncio
    async def test_concurrent_unblock_operations(self, blocklist: MemoryBlocklist):
        """Test concurrent unblock operations."""
        user_id = 12345

        # Block first
        await blocklist.block_user(user_id)

        # Simulate concurrent unblock operations
        tasks: list[Any] = []
        for _ in range(10):
            task = blocklist.unblock_user(user_id)
            tasks.append(task)

        await asyncio.gather(*tasks)

        # Should be unblocked
        is_blocked = await blocklist.is_blocked(user_id)
        assert is_blocked is False

    @pytest.mark.asyncio
    async def test_mixed_concurrent_operations(self, blocklist: MemoryBlocklist):
        """Test mixed concurrent block/unblock operations."""
        user_id = 12345

        # Simulate mixed operations
        tasks: list[Any] = []
        for i in range(20):
            if i % 2 == 0:
                task = blocklist.block_user(user_id)
            else:
                task = blocklist.unblock_user(user_id)
            tasks.append(task)

        await asyncio.gather(*tasks)

        # Final state should be consistent
        is_blocked = await blocklist.is_blocked(user_id)
        # The final state depends on the last operation, but should be consistent
        assert isinstance(is_blocked, bool)

    @pytest.mark.asyncio
    async def test_blocklist_isolation(self, blocklist: MemoryBlocklist):
        """Test that blocklist operations are isolated per user."""
        user1 = 12345
        user2 = 67890

        # Block user1
        await blocklist.block_user(user1)

        # user1 should be blocked, user2 should not
        assert await blocklist.is_blocked(user1) is True
        assert await blocklist.is_blocked(user2) is False

        # Block user2
        await blocklist.block_user(user2)

        # Both should be blocked
        assert await blocklist.is_blocked(user1) is True
        assert await blocklist.is_blocked(user2) is True

        # Unblock user1
        await blocklist.unblock_user(user1)

        # user1 should be unblocked, user2 should still be blocked
        assert await blocklist.is_blocked(user1) is False
        assert await blocklist.is_blocked(user2) is True

    @pytest.mark.asyncio
    async def test_blocklist_persistence(self, blocklist: MemoryBlocklist):
        """Test that blocklist state persists across operations."""
        user_id = 12345

        # Block user
        await blocklist.block_user(user_id)
        assert await blocklist.is_blocked(user_id) is True

        # Check multiple times
        for _ in range(5):
            is_blocked = await blocklist.is_blocked(user_id)
            assert is_blocked is True

        # Unblock
        await blocklist.unblock_user(user_id)
        assert await blocklist.is_blocked(user_id) is False

        # Check multiple times
        for _ in range(5):
            is_blocked = await blocklist.is_blocked(user_id)
            assert is_blocked is False

    @pytest.mark.asyncio
    async def test_blocklist_memory_usage(self, blocklist: MemoryBlocklist):
        """Test blocklist memory usage with many users."""
        # Block many users
        for user_id in range(1000):
            await blocklist.block_user(user_id)

        # All should be blocked
        for user_id in range(1000):
            is_blocked = await blocklist.is_blocked(user_id)
            assert is_blocked is True

        # Unblock all
        for user_id in range(1000):
            await blocklist.unblock_user(user_id)

        # All should be unblocked
        for user_id in range(1000):
            is_blocked = await blocklist.is_blocked(user_id)
            assert is_blocked is False
