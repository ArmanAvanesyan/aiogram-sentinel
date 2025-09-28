"""Unit tests for DebounceMiddleware."""

from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from aiogram_sentinel.middlewares.debouncing import DebounceMiddleware


@pytest.mark.unit
class TestDebounceMiddleware:
    """Test DebounceMiddleware functionality."""

    @pytest.mark.asyncio
    async def test_first_message_passes(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that first message passes through."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)

        # Should not set debounced flag
        assert "sentinel_debounced" not in mock_data

    @pytest.mark.asyncio
    async def test_duplicate_message_blocked(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that duplicate messages are blocked."""
        # Mock debounced message
        mock_debounce_backend.seen.return_value = True

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should not call handler
        mock_handler.assert_not_called()

        # Should return None (blocked)
        assert result is None

        # Should set debounced flag
        assert mock_data["sentinel_debounced"] is True

    @pytest.mark.asyncio
    async def test_debounce_key_generation(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test debounce key generation."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should check debounce with generated key
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        assert len(call_args) == 3  # key, window_seconds, fingerprint
        key = call_args[0]

        # Key should contain user ID and handler name
        assert "12345" in key  # User ID from mock_message
        assert "AsyncMock" in key  # Handler name from mock_handler

    @pytest.mark.asyncio
    async def test_debounce_with_custom_delay(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test debouncing with custom delay from decorator."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        # Set custom delay on handler
        mock_handler.sentinel_debounce = (5, None)

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should check debounce with custom window
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        assert call_args[1] == 5  # Custom window (from tuple)

    @pytest.mark.asyncio
    async def test_debounce_with_default_delay(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test debouncing with default delay."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=2)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should check debounce with default window
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        assert call_args[1] == 2  # Default window

    @pytest.mark.asyncio
    async def test_debounce_with_callback_query(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_callback_query: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test debouncing with callback query."""
        # Mock non-debounced callback
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        result = await middleware(mock_handler, mock_callback_query, mock_data)

        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_callback_query, mock_data)

    @pytest.mark.asyncio
    async def test_debounce_key_with_fingerprint(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test debounce key generation with message fingerprint."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should check debounce with key containing fingerprint
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        key = call_args[0]

        # Key should contain user ID and handler name
        assert "12345" in key  # User ID
        assert "AsyncMock" in key  # Handler name

    @pytest.mark.asyncio
    async def test_debounce_key_with_callback_data(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_callback_query: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test debounce key generation with callback data."""
        # Mock non-debounced callback
        mock_debounce_backend.is_debounced.return_value = False
        mock_debounce_backend.get_debounce.return_value = None

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        await middleware(mock_handler, mock_callback_query, mock_data)

        # Should check debounce with key containing callback data
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        key = call_args[0]

        # Key should contain user ID and handler name
        assert "12345" in key  # User ID
        assert "AsyncMock" in key  # Handler name

    @pytest.mark.asyncio
    async def test_debounce_backend_error(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test handling when debounce backend raises an error."""
        # Mock backend error
        mock_debounce_backend.seen.side_effect = Exception("Backend error")

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Should raise the error
        with pytest.raises(Exception, match="Backend error"):
            await middleware(mock_handler, mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_handler_error_propagation(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that handler errors are propagated."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        # Mock handler error
        mock_handler.side_effect = Exception("Handler error")

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Should propagate handler error
        with pytest.raises(Exception, match="Handler error"):
            await middleware(mock_handler, mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_data_preservation(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that data dictionary is preserved."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        # Add some data
        mock_data["existing_key"] = "existing_value"

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should preserve existing data
        assert mock_data["existing_key"] == "existing_value"

    @pytest.mark.asyncio
    async def test_debounced_flag_preservation(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that existing debounced flag is preserved."""
        # Mock debounced message
        mock_debounce_backend.seen.return_value = True

        # Set existing debounced flag
        mock_data["sentinel_debounced"] = "existing_value"

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should overwrite the flag when message is debounced
        assert mock_data["sentinel_debounced"] is True

    @pytest.mark.asyncio
    async def test_multiple_events_same_content(
        self, mock_debounce_backend: Mock, mock_handler: Mock, mock_data: dict[str, Any]
    ) -> None:
        """Test processing multiple events with same content."""
        # Mock first message as non-debounced, second as debounced
        mock_debounce_backend.seen.side_effect = [False, True]

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Create two messages with same content
        mock_message1 = MagicMock()
        mock_message1.from_user.id = 12345
        mock_message1.text = "same text"

        mock_message2 = MagicMock()
        mock_message2.from_user.id = 12345
        mock_message2.text = "same text"

        # Process first message
        result1 = await middleware(mock_handler, mock_message1, mock_data)
        assert result1 == "handler_result"

        # Process second message
        result2 = await middleware(mock_handler, mock_message2, mock_data)
        assert result2 is None
        assert mock_data["sentinel_debounced"] is True

    @pytest.mark.asyncio
    async def test_different_users_same_content(
        self, mock_debounce_backend: Mock, mock_handler: Mock, mock_data: dict[str, Any]
    ) -> None:
        """Test processing events for different users with same content."""
        # Mock non-debounced messages
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Create messages for different users with same content
        user_ids = [12345, 67890]
        events: list[Any] = []

        for user_id in user_ids:
            mock_event = MagicMock()
            mock_event.from_user.id = user_id
            mock_event.text = "same text"
            events.append(mock_event)

        # Process all events
        for event in events:
            result = await middleware(mock_handler, event, mock_data)
            assert result == "handler_result"

        # Should check debounce for each user
        assert mock_debounce_backend.seen.call_count == 2

    @pytest.mark.asyncio
    async def test_middleware_initialization(self, mock_debounce_backend: Mock) -> None:
        """Test middleware initialization."""
        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Should store the backend and delay
        assert hasattr(middleware, "_debounce_backend")
        assert hasattr(middleware, "_default_delay")

    @pytest.mark.asyncio
    async def test_edge_case_empty_message_text(
        self, mock_debounce_backend: Mock, mock_handler: Mock, mock_data: dict[str, Any]
    ) -> None:
        """Test handling with empty message text."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Create message with empty text
        mock_message = MagicMock()
        mock_message.from_user.id = 12345
        mock_message.text = ""

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should work normally
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_edge_case_none_message_text(
        self, mock_debounce_backend: Mock, mock_handler: Mock, mock_data: dict[str, Any]
    ) -> None:
        """Test handling with None message text."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Create message with None text
        mock_message = MagicMock()
        mock_message.from_user.id = 12345
        mock_message.text = None

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should work normally
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_edge_case_no_user_id(
        self, mock_debounce_backend: Mock, mock_handler: Mock, mock_data: dict[str, Any]
    ) -> None:
        """Test handling when no user ID is available."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        middleware = DebounceMiddleware(mock_debounce_backend, cfg)

        # Create event with no user information
        mock_event = MagicMock()
        mock_event.from_user = None
        mock_event.text = "test"

        # Process event
        result = await middleware(mock_handler, mock_event, mock_data)

        # Should work normally (use 0 as user ID)
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_event, mock_data)
