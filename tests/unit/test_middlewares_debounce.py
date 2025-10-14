"""Unit tests for DebounceMiddleware."""

from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from aiogram_sentinel.middlewares.debouncing import DebounceMiddleware
from aiogram_sentinel.policy import DebounceCfg
from aiogram_sentinel.scopes import KeyBuilder, Scope


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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

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
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

        # Create event with no user information
        mock_event = MagicMock()
        mock_event.from_user = None
        mock_event.text = "test"

        # Process event
        result = await middleware(mock_handler, mock_event, mock_data)

        # Should work normally (use 0 as user ID)
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_event, mock_data)


@pytest.mark.unit
class TestDebounceMiddlewarePolicySupport:
    """Test DebounceMiddleware policy support."""

    @pytest.mark.asyncio
    async def test_policy_based_configuration(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that policy-based configuration is used."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

        # Add policy-based configuration to data
        debounce_cfg = DebounceCfg(window=3, scope=Scope.USER)
        mock_data["sentinel_debounce_cfg"] = debounce_cfg

        # Mock user ID for USER scope
        mock_data["user_id"] = 123

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)

        # Should use policy configuration (3 second window)
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        assert call_args[1] == 3  # window from policy

    @pytest.mark.asyncio
    async def test_policy_scope_cap_enforcement(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that policy scope cap is enforced."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

        # Add policy with USER scope cap
        debounce_cfg = DebounceCfg(window=2, scope=Scope.USER)
        mock_data["sentinel_debounce_cfg"] = debounce_cfg

        # Mock user and chat IDs
        mock_data["user_id"] = 123
        mock_data["chat_id"] = 456

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should call handler
        assert result == "handler_result"

        # Should use USER scope (most specific within USER cap)
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        key = call_args[0]
        assert "USER" in key
        assert "123" in key  # user_id

    @pytest.mark.asyncio
    async def test_policy_scope_cap_violation_skips_policy(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that policy is skipped when scope cap cannot be satisfied."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

        # Add policy with USER scope cap but no user_id available
        debounce_cfg = DebounceCfg(window=2, scope=Scope.USER)
        mock_data["sentinel_debounce_cfg"] = debounce_cfg

        # Mock only chat_id (no user_id) - create message without from_user
        mock_data["chat_id"] = 456
        # Create a message without from_user to simulate no user_id available
        from datetime import datetime

        from aiogram.types import Chat
        from aiogram.types import Message as TelegramMessage

        # Create a group chat (not private) so chat_id != user_id
        group_chat = Chat(id=456, type="group", title="Test Group")
        message_without_user = TelegramMessage(
            message_id=1, date=datetime.now(), chat=group_chat, text="test"
        )

        # Process event
        result = await middleware(mock_handler, message_without_user, mock_data)

        # Should call handler (policy skipped, uses default config)
        assert result == "handler_result"

        # Should use default configuration (1 second window)
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        assert call_args[1] == 1  # default window

    @pytest.mark.asyncio
    async def test_policy_method_and_bucket_usage(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that policy method and bucket are used in key generation."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

        # Add policy with method and bucket
        debounce_cfg = DebounceCfg(
            window=2, scope=Scope.USER, method="sendMessage", bucket="test_bucket"
        )
        mock_data["sentinel_debounce_cfg"] = debounce_cfg

        # Mock user ID
        mock_data["user_id"] = 123

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should call handler
        assert result == "handler_result"

        # Should use method and bucket in key generation
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        key = call_args[0]
        assert "m=sendMessage" in key
        assert "b=test_bucket" in key

    @pytest.mark.asyncio
    async def test_policy_backward_compatibility_with_handler_attributes(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test backward compatibility with handler attributes."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

        # Add handler with legacy attributes (no policy config)
        mock_handler.sentinel_debounce = (5, "chat")

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should call handler
        assert result == "handler_result"

        # Should use handler attributes (5 second window)
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        assert call_args[1] == 5  # window from handler

    @pytest.mark.asyncio
    async def test_policy_precedence_over_handler_attributes(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that policy configuration takes precedence over handler attributes."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=1)
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

        # Add policy configuration
        debounce_cfg = DebounceCfg(window=3)
        mock_data["sentinel_debounce_cfg"] = debounce_cfg

        # Add handler with legacy attributes
        mock_handler.sentinel_debounce = (5, "chat")

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should call handler
        assert result == "handler_result"

        # Should use policy configuration (3 second window), not handler attributes
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        assert call_args[1] == 3  # window from policy

    @pytest.mark.asyncio
    async def test_policy_fallback_to_defaults(
        self,
        mock_debounce_backend: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test fallback to defaults when no policy or handler attributes."""
        # Mock non-debounced message
        mock_debounce_backend.seen.return_value = False

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(debounce_default_window=2)
        key_builder = KeyBuilder(app="test")
        middleware = DebounceMiddleware(mock_debounce_backend, cfg, key_builder)

        # No policy config or handler attributes

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should call handler
        assert result == "handler_result"

        # Should use default configuration
        mock_debounce_backend.seen.assert_called_once()
        call_args = mock_debounce_backend.seen.call_args[0]
        assert call_args[1] == 2  # default window
