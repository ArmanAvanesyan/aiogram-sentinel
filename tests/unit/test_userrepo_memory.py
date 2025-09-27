"""Unit tests for MemoryUserRepo."""

import asyncio
import pytest
from unittest.mock import patch

from aiogram_sentinel.storage.memory import MemoryUserRepo


@pytest.mark.unit
class TestMemoryUserRepo:
    """Test MemoryUserRepo functionality."""

    @pytest.mark.asyncio
    async def test_is_registered_false(self, user_repo):
        """Test is_registered returns False for new user."""
        user_id = 12345
        
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is False

    @pytest.mark.asyncio
    async def test_register_user(self, user_repo, mock_time):
        """Test registering a new user."""
        user_id = 12345
        username = "testuser"
        
        await user_repo.register_user(user_id, username=username)
        
        # Should be registered
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is True

    @pytest.mark.asyncio
    async def test_get_user(self, user_repo, mock_time):
        """Test getting user data."""
        user_id = 12345
        username = "testuser"
        first_name = "Test"
        
        # Register user
        await user_repo.register_user(user_id, username=username, first_name=first_name)
        
        # Get user data
        user_data = await user_repo.get_user(user_id)
        assert user_data is not None
        assert user_data["username"] == username
        assert user_data["first_name"] == first_name
        assert "registered_at" in user_data

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self, user_repo):
        """Test getting data for non-existent user."""
        user_id = 12345
        
        user_data = await user_repo.get_user(user_id)
        assert user_data is None

    @pytest.mark.asyncio
    async def test_register_user_idempotency(self, user_repo, mock_time):
        """Test that registering the same user multiple times is idempotent."""
        user_id = 12345
        username = "testuser"
        
        # Register user multiple times
        await user_repo.register_user(user_id, username=username)
        await user_repo.register_user(user_id, username=username)
        await user_repo.register_user(user_id, username=username)
        
        # Should still be registered
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is True
        
        # Should have only one entry
        user_data = await user_repo.get_user(user_id)
        assert user_data is not None
        assert user_data["username"] == username

    @pytest.mark.asyncio
    async def test_register_user_with_different_data(self, user_repo, mock_time):
        """Test registering user with different data updates existing entry."""
        user_id = 12345
        
        # Register with initial data
        await user_repo.register_user(user_id, username="olduser", first_name="Old")
        
        # Register with updated data
        await user_repo.register_user(user_id, username="newuser", first_name="New", last_name="User")
        
        # Should have updated data
        user_data = await user_repo.get_user(user_id)
        assert user_data["username"] == "newuser"
        assert user_data["first_name"] == "New"
        assert user_data["last_name"] == "User"

    @pytest.mark.asyncio
    async def test_register_user_minimal_data(self, user_repo, mock_time):
        """Test registering user with minimal data."""
        user_id = 12345
        
        # Register with only user_id
        await user_repo.register_user(user_id)
        
        # Should be registered
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is True
        
        # Should have minimal data
        user_data = await user_repo.get_user(user_id)
        assert user_data is not None
        assert "registered_at" in user_data
        assert "user_id" in user_data
        assert len(user_data) == 2  # registered_at and user_id

    @pytest.mark.asyncio
    async def test_register_user_with_all_fields(self, user_repo, mock_time):
        """Test registering user with all possible fields."""
        user_id = 12345
        user_data = {
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "language_code": "en",
            "is_bot": False,
            "is_premium": True,
            "custom_field": "custom_value"
        }
        
        # Register with all data
        await user_repo.register_user(user_id, **user_data)
        
        # Should be registered
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is True
        
        # Should have all data
        retrieved_data = await user_repo.get_user(user_id)
        assert retrieved_data is not None
        
        for key, value in user_data.items():
            assert retrieved_data[key] == value
        
        assert "registered_at" in retrieved_data

    @pytest.mark.asyncio
    async def test_multiple_users(self, user_repo, mock_time):
        """Test handling multiple users."""
        users = [
            (12345, "user1", "User", "One"),
            (67890, "user2", "User", "Two"),
            (11111, "user3", "User", "Three"),
        ]
        
        # Register all users
        for user_id, username, first_name, last_name in users:
            await user_repo.register_user(user_id, username=username, first_name=first_name, last_name=last_name)
        
        # All should be registered
        for user_id, username, first_name, last_name in users:
            is_registered = await user_repo.is_registered(user_id)
            assert is_registered is True
            
            user_data = await user_repo.get_user(user_id)
            assert user_data["username"] == username
            assert user_data["first_name"] == first_name
            assert user_data["last_name"] == last_name

    @pytest.mark.asyncio
    async def test_edge_case_zero_user_id(self, user_repo, mock_time):
        """Test edge case with zero user ID."""
        user_id = 0
        
        # Register user with ID 0
        await user_repo.register_user(user_id, username="zerouser")
        
        # Should be registered
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is True
        
        user_data = await user_repo.get_user(user_id)
        assert user_data["username"] == "zerouser"

    @pytest.mark.asyncio
    async def test_edge_case_negative_user_id(self, user_repo, mock_time):
        """Test edge case with negative user ID."""
        user_id = -12345
        
        # Register user with negative ID
        await user_repo.register_user(user_id, username="neguser")
        
        # Should be registered
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is True
        
        user_data = await user_repo.get_user(user_id)
        assert user_data["username"] == "neguser"

    @pytest.mark.asyncio
    async def test_edge_case_large_user_id(self, user_repo, mock_time):
        """Test edge case with large user ID."""
        user_id = 999999999999
        
        # Register user with large ID
        await user_repo.register_user(user_id, username="largeuser")
        
        # Should be registered
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is True
        
        user_data = await user_repo.get_user(user_id)
        assert user_data["username"] == "largeuser"

    @pytest.mark.asyncio
    async def test_concurrent_register_operations(self, user_repo, mock_time):
        """Test concurrent register operations."""
        user_id = 12345
        
        # Simulate concurrent register operations
        tasks = []
        for i in range(10):
            task = user_repo.register_user(user_id, username=f"user{i}")
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Should be registered
        is_registered = await user_repo.is_registered(user_id)
        assert is_registered is True
        
        # Should have data from last operation
        user_data = await user_repo.get_user(user_id)
        assert user_data is not None

    @pytest.mark.asyncio
    async def test_concurrent_get_operations(self, user_repo, mock_time):
        """Test concurrent get operations."""
        user_id = 12345
        
        # Register user first
        await user_repo.register_user(user_id, username="testuser")
        
        # Simulate concurrent get operations
        tasks = []
        for _ in range(10):
            task = user_repo.get_user(user_id)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # All should return the same data
        for result in results:
            assert result is not None
            assert result["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_user_data_types(self, user_repo, mock_time):
        """Test user data with different types."""
        user_id = 12345
        user_data = {
            "string_field": "string_value",
            "int_field": 42,
            "float_field": 3.14,
            "bool_field": True,
            "list_field": [1, 2, 3],
            "dict_field": {"nested": "value"},
            "none_field": None,
        }
        
        # Register with various data types
        await user_repo.register_user(user_id, **user_data)
        
        # Retrieve and verify types
        retrieved_data = await user_repo.get_user(user_id)
        assert retrieved_data["string_field"] == "string_value"
        assert retrieved_data["int_field"] == 42
        assert retrieved_data["float_field"] == 3.14
        assert retrieved_data["bool_field"] is True
        assert retrieved_data["list_field"] == [1, 2, 3]
        assert retrieved_data["dict_field"] == {"nested": "value"}
        assert retrieved_data["none_field"] is None

    @pytest.mark.asyncio
    async def test_registered_at_timestamp(self, user_repo, mock_time):
        """Test that registered_at timestamp is set correctly."""
        user_id = 12345
        
        # Register user
        await user_repo.register_user(user_id, username="testuser")
        
        # Check timestamp
        user_data = await user_repo.get_user(user_id)
        assert "registered_at" in user_data
        assert user_data["registered_at"] == 1000.0  # From mock_time fixture

    @pytest.mark.asyncio
    async def test_user_isolation(self, user_repo, mock_time):
        """Test that user data is isolated per user."""
        user1 = 12345
        user2 = 67890
        
        # Register different users with different data
        await user_repo.register_user(user1, username="user1", first_name="User1")
        await user_repo.register_user(user2, username="user2", first_name="User2")
        
        # Get data for each user
        data1 = await user_repo.get_user(user1)
        data2 = await user_repo.get_user(user2)
        
        # Data should be different
        assert data1["username"] == "user1"
        assert data1["first_name"] == "User1"
        assert data2["username"] == "user2"
        assert data2["first_name"] == "User2"
        
        # Should be registered
        assert await user_repo.is_registered(user1) is True
        assert await user_repo.is_registered(user2) is True
