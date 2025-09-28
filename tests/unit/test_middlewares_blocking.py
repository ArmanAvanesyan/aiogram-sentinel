"""Unit tests for BlockingMiddleware."""

from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from aiogram_sentinel.middlewares.blocking import BlockingMiddleware


@pytest.mark.unit
class TestBlockingMiddleware:
    """Test BlockingMiddleware functionality."""

    @pytest.mark.asyncio
    async def test_non_blocked_user_passes(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that non-blocked users pass through."""
        # Mock non-blocked user
        mock_blocklist_backend.is_blocked.return_value = False

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)

        # Should not set blocked flag
        assert "sentinel_blocked" not in mock_data

    @pytest.mark.asyncio
    async def test_blocked_user_short_circuit(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that blocked users are short-circuited."""
        # Mock blocked user
        mock_blocklist_backend.is_blocked.return_value = True

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should not call handler
        mock_handler.assert_not_called()

        # Should return None (short-circuit)
        assert result is None

        # Should set blocked flag
        assert mock_data["sentinel_blocked"] is True

    @pytest.mark.asyncio
    async def test_extract_user_id_from_message(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test user ID extraction from message."""
        # Mock non-blocked user
        mock_blocklist_backend.is_blocked.return_value = False

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Create message with user
        mock_message = MagicMock()
        mock_message.from_user.id = 12345

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should check blocklist with correct user ID
        mock_blocklist_backend.is_blocked.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_extract_user_id_from_callback_query(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test user ID extraction from callback query."""
        # Mock non-blocked user
        mock_blocklist_backend.is_blocked.return_value = False

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Create callback query with user
        mock_callback = MagicMock()
        mock_callback.from_user.id = 67890

        # Process event
        await middleware(mock_handler, mock_callback, mock_data)

        # Should check blocklist with correct user ID
        mock_blocklist_backend.is_blocked.assert_called_once_with(67890)

    @pytest.mark.asyncio
    async def test_extract_user_id_from_chat(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test user ID extraction from chat (fallback)."""
        # Mock non-blocked user
        mock_blocklist_backend.is_blocked.return_value = False

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Create event with only chat
        mock_event = MagicMock()
        mock_event.from_user = None
        mock_event.user = None
        mock_event.chat.id = 11111

        # Process event
        await middleware(mock_handler, mock_event, mock_data)

        # Should check blocklist with chat ID
        mock_blocklist_backend.is_blocked.assert_called_once_with(11111)

    @pytest.mark.asyncio
    async def test_no_user_id_available(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test handling when no user ID is available."""
        # Mock non-blocked user
        mock_blocklist_backend.is_blocked.return_value = False

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Create event with no user information
        mock_event = MagicMock()
        mock_event.from_user = None
        mock_event.user = None
        mock_event.chat = None

        # Process event
        result = await middleware(mock_handler, mock_event, mock_data)

        # Should skip blocking check for anonymous users and call handler
        mock_blocklist_backend.is_blocked.assert_not_called()
        mock_handler.assert_called_once_with(mock_event, mock_data)
        assert result == "handler_result"

    @pytest.mark.asyncio
    async def test_blocklist_backend_error(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test handling when blocklist backend raises an error."""
        # Mock backend error
        mock_blocklist_backend.is_blocked.side_effect = Exception("Backend error")

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Should raise the error
        with pytest.raises(Exception, match="Backend error"):
            await middleware(mock_handler, mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_handler_error_propagation(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that handler errors are propagated."""
        # Mock non-blocked user
        mock_blocklist_backend.is_blocked.return_value = False

        # Mock handler error
        mock_handler.side_effect = Exception("Handler error")

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Should propagate handler error
        with pytest.raises(Exception, match="Handler error"):
            await middleware(mock_handler, mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_data_preservation(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that data dictionary is preserved."""
        # Mock non-blocked user
        mock_blocklist_backend.is_blocked.return_value = False

        # Add some data
        mock_data["existing_key"] = "existing_value"

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should preserve existing data
        assert mock_data["existing_key"] == "existing_value"

    @pytest.mark.asyncio
    async def test_blocked_flag_preservation(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that existing blocked flag is preserved."""
        # Mock blocked user
        mock_blocklist_backend.is_blocked.return_value = True

        # Set existing blocked flag
        mock_data["sentinel_blocked"] = "existing_value"

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should overwrite the flag when user is blocked
        assert mock_data["sentinel_blocked"] is True

    @pytest.mark.asyncio
    async def test_multiple_events_same_user(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test processing multiple events for the same user."""
        # Mock non-blocked user
        mock_blocklist_backend.is_blocked.return_value = False

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Create multiple events for same user
        events: list[Any] = []
        for _i in range(5):
            mock_event = MagicMock()
            mock_event.from_user.id = 12345
            events.append(mock_event)

        # Process all events
        for event in events:
            await middleware(mock_handler, event, mock_data)

        # Should check blocklist for each event
        assert mock_blocklist_backend.is_blocked.call_count == 5

        # All calls should be with same user ID
        for call in mock_blocklist_backend.is_blocked.call_args_list:
            assert call[0][0] == 12345

    @pytest.mark.asyncio
    async def test_different_users(
        self,
        mock_blocklist_backend: Mock,
        mock_handler: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test processing events for different users."""
        # Mock non-blocked users
        mock_blocklist_backend.is_blocked.return_value = False

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Create events for different users
        user_ids = [12345, 67890, 11111]
        events: list[Any] = []

        for user_id in user_ids:
            mock_event = MagicMock()
            mock_event.from_user.id = user_id
            events.append(mock_event)

        # Process all events
        for event in events:
            await middleware(mock_handler, event, mock_data)

        # Should check blocklist for each user
        assert mock_blocklist_backend.is_blocked.call_count == 3

        # Check that all user IDs were checked
        called_user_ids = [
            call[0][0] for call in mock_blocklist_backend.is_blocked.call_args_list
        ]
        assert set(called_user_ids) == set(user_ids)

    @pytest.mark.asyncio
    async def test_middleware_initialization(
        self, mock_blocklist_backend: Mock
    ) -> None:
        """Test middleware initialization."""
        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Should store the backend
        assert hasattr(middleware, "_blocklist_backend")

    @pytest.mark.asyncio
    async def test_edge_case_empty_data(
        self, mock_blocklist_backend: Mock, mock_handler: Mock, mock_message: Mock
    ) -> None:
        """Test handling with empty data dictionary."""
        # Mock non-blocked user
        mock_blocklist_backend.is_blocked.return_value = False

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Process with empty data
        data: dict[str, Any] = {}
        result = await middleware(mock_handler, mock_message, data)

        # Should work normally
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, data)

    @pytest.mark.asyncio
    async def test_edge_case_none_data(
        self, mock_blocklist_backend: Mock, mock_handler: Mock, mock_message: Mock
    ) -> None:
        """Test handling with None data."""
        # Mock blocked user to trigger data access
        mock_blocklist_backend.is_blocked.return_value = True

        middleware = BlockingMiddleware(mock_blocklist_backend)

        # Process with None data
        data: Any = None

        # Should raise error when trying to set data["sentinel_blocked"]
        with pytest.raises(TypeError):
            await middleware(mock_handler, mock_message, data)
