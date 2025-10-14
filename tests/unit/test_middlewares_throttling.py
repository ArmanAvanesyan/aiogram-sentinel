"""Unit tests for ThrottlingMiddleware."""

from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from aiogram_sentinel.middlewares.throttling import ThrottlingMiddleware
from aiogram_sentinel.scopes import KeyBuilder


@pytest.mark.unit
class TestThrottlingMiddleware:
    """Test ThrottlingMiddleware functionality."""

    @pytest.mark.asyncio
    async def test_allowed_request_passes(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that allowed requests pass through."""
        # Mock allowed request
        mock_rate_limiter.allow.return_value = True
        mock_rate_limiter.get_remaining.return_value = 5  # Under limit

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)

        # Should not set rate limited flag
        assert "sentinel_rate_limited" not in mock_data

    @pytest.mark.asyncio
    async def test_rate_limited_request_blocked(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that rate limited requests are blocked."""
        # Mock rate limited request
        mock_rate_limiter.allow.return_value = False  # Over limit
        mock_rate_limiter.get_remaining.return_value = 0  # No remaining

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)

        # Should not call handler
        mock_handler.assert_not_called()

        # Should return None (blocked)
        assert result is None

        # Should set rate limited flag
        assert mock_data["sentinel_rate_limited"] is True

    @pytest.mark.asyncio
    async def test_rate_limit_key_generation(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test rate limit key generation."""
        # Mock allowed request
        mock_rate_limiter.increment_rate_limit.return_value = 5
        mock_rate_limiter.get_rate_limit.return_value = 5

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should check rate limit with generated key
        mock_rate_limiter.allow.assert_called_once()
        call_args = mock_rate_limiter.allow.call_args[0]
        assert len(call_args) == 3  # key, max_events, per_seconds
        key, max_events, per_seconds = call_args

        # Key should contain user ID and handler name
        assert "12345" in key  # User ID from mock_message
        assert "AsyncMock" in key  # Handler name from mock_handler

        # Config should be default
        assert max_events == 10
        assert per_seconds == 60

    @pytest.mark.asyncio
    async def test_rate_limit_with_custom_config(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test rate limiting with custom config from decorator."""
        # Mock allowed request
        mock_rate_limiter.increment_rate_limit.return_value = 3

        # Set custom rate limit on handler
        mock_handler.sentinel_rate_limit = (5, 30, None)

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should increment rate limit with custom window
        mock_rate_limiter.allow.assert_called_once()
        call_args = mock_rate_limiter.allow.call_args[0]
        _key, _max_events, per_seconds = call_args
        assert per_seconds == 30  # Custom window

    @pytest.mark.asyncio
    async def test_rate_limit_with_default_config(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test rate limiting with default config."""
        # Mock allowed request
        mock_rate_limiter.increment_rate_limit.return_value = 5
        mock_rate_limiter.get_rate_limit.return_value = 5

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=20, throttling_default_per_seconds=120
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should increment rate limit with default window
        mock_rate_limiter.allow.assert_called_once()
        call_args = mock_rate_limiter.allow.call_args[0]
        _key, _max_events, per_seconds = call_args
        assert per_seconds == 120  # Default window

    @pytest.mark.asyncio
    async def test_on_rate_limited_hook_called(
        self,
        mock_rate_limiter: Mock,
        mock_on_rate_limited: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that on_rate_limited hook is called when rate limited."""
        # Mock rate limited request
        mock_rate_limiter.allow.return_value = False  # Over limit
        mock_rate_limiter.get_remaining.return_value = 0  # No remaining

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(
            mock_rate_limiter, cfg, key_builder, on_rate_limited=mock_on_rate_limited
        )

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should call the hook
        mock_on_rate_limited.assert_called_once()
        call_args = mock_on_rate_limited.call_args[0]
        assert len(call_args) == 3
        event, data, retry_after = call_args

        assert event is mock_message
        assert data is mock_data
        assert isinstance(retry_after, float)
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_on_rate_limited_hook_not_called_when_allowed(
        self,
        mock_rate_limiter: Mock,
        mock_on_rate_limited: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that on_rate_limited hook is not called when request is allowed."""
        # Mock allowed request
        mock_rate_limiter.increment_rate_limit.return_value = 5
        mock_rate_limiter.get_rate_limit.return_value = 5

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(
            mock_rate_limiter, cfg, key_builder, on_rate_limited=mock_on_rate_limited
        )

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should not call the hook
        mock_on_rate_limited.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_rate_limited_hook_error_handling(
        self,
        mock_rate_limiter: Mock,
        mock_on_rate_limited: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that hook errors don't break middleware."""
        # Mock rate limited request
        mock_rate_limiter.allow.return_value = False

        # Mock hook error
        mock_on_rate_limited.side_effect = Exception("Hook error")

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(
            mock_rate_limiter, cfg, key_builder, on_rate_limited=mock_on_rate_limited
        )

        # Should not raise error
        result = await middleware(mock_handler, mock_message, mock_data)
        assert result is None
        assert mock_data["sentinel_rate_limited"] is True

    @pytest.mark.asyncio
    async def test_rate_limiter_backend_error(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test handling when rate limiter backend raises an error."""
        # Mock backend error
        mock_rate_limiter.allow.side_effect = Exception("Backend error")

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Should raise the error
        with pytest.raises(Exception, match="Backend error"):
            await middleware(mock_handler, mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_handler_error_propagation(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that handler errors are propagated."""
        # Mock allowed request
        mock_rate_limiter.increment_rate_limit.return_value = 5
        mock_rate_limiter.get_rate_limit.return_value = 5

        # Mock handler error
        mock_handler.side_effect = Exception("Handler error")

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Should propagate handler error
        with pytest.raises(Exception, match="Handler error"):
            await middleware(mock_handler, mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_data_preservation(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that data dictionary is preserved."""
        # Mock allowed request
        mock_rate_limiter.increment_rate_limit.return_value = 5
        mock_rate_limiter.get_rate_limit.return_value = 5

        # Add some data
        mock_data["existing_key"] = "existing_value"

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should preserve existing data
        assert mock_data["existing_key"] == "existing_value"

    @pytest.mark.asyncio
    async def test_rate_limited_flag_preservation(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test that existing rate limited flag is preserved."""
        # Mock rate limited request
        mock_rate_limiter.increment_rate_limit.return_value = 11

        # Set existing rate limited flag
        mock_data["sentinel_rate_limited"] = "existing_value"

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Process event
        await middleware(mock_handler, mock_message, mock_data)

        # Should preserve existing flag
        assert mock_data["sentinel_rate_limited"] == "existing_value"

    @pytest.mark.asyncio
    async def test_multiple_events_same_user(
        self, mock_rate_limiter: Mock, mock_handler: Mock, mock_data: dict[str, Any]
    ) -> None:
        """Test processing multiple events for the same user."""
        # Mock requests under limit
        mock_rate_limiter.increment_rate_limit.return_value = 5

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Create multiple events for same user
        events: list[Any] = []
        for _i in range(5):
            mock_event = MagicMock()
            mock_event.from_user.id = 12345
            events.append(mock_event)

        # Process all events
        for event in events:
            result = await middleware(mock_handler, event, mock_data)
            assert result == "handler_result"

        # Should increment rate limit for each event
        assert mock_rate_limiter.allow.call_count == 5

    @pytest.mark.asyncio
    async def test_different_users(
        self, mock_rate_limiter: Mock, mock_handler: Mock, mock_data: dict[str, Any]
    ) -> None:
        """Test processing events for different users."""
        # Mock requests under limit
        mock_rate_limiter.increment_rate_limit.return_value = 5

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Create events for different users
        user_ids = [12345, 67890, 11111]
        events: list[Any] = []

        for user_id in user_ids:
            mock_event = MagicMock()
            mock_event.from_user.id = user_id
            events.append(mock_event)

        # Process all events
        for event in events:
            result = await middleware(mock_handler, event, mock_data)
            assert result == "handler_result"

        # Should increment rate limit for each user
        assert mock_rate_limiter.allow.call_count == 3

    @pytest.mark.asyncio
    async def test_middleware_initialization(self, mock_rate_limiter: Mock) -> None:
        """Test middleware initialization."""
        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Should store the backend and config
        assert hasattr(middleware, "_rate_limiter")
        assert hasattr(middleware, "_default_limit")
        assert hasattr(middleware, "_default_window")

    @pytest.mark.asyncio
    async def test_edge_case_no_user_id(
        self, mock_rate_limiter: Mock, mock_handler: Mock, mock_data: dict[str, Any]
    ) -> None:
        """Test handling when no user ID is available."""
        # Mock allowed request
        mock_rate_limiter.increment_rate_limit.return_value = 5
        mock_rate_limiter.get_rate_limit.return_value = 5

        from aiogram_sentinel.config import SentinelConfig

        cfg = SentinelConfig(
            throttling_default_max=10, throttling_default_per_seconds=60
        )
        key_builder = KeyBuilder(app="test")
        middleware = ThrottlingMiddleware(mock_rate_limiter, cfg, key_builder)

        # Create event with no user information
        mock_event = MagicMock()
        mock_event.from_user = None

        # Process event
        result = await middleware(mock_handler, mock_event, mock_data)

        # Should work normally (use 0 as user ID)
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_event, mock_data)

    @pytest.mark.asyncio
    async def test_edge_case_zero_limit(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test handling with zero rate limit."""
        # Mock rate limited request
        mock_rate_limiter.allow.return_value = False

        from aiogram_sentinel.config import SentinelConfig
        from aiogram_sentinel.exceptions import ConfigurationError

        # Should raise configuration error for zero limit
        with pytest.raises(
            ConfigurationError, match="throttling_default_max must be positive"
        ):
            SentinelConfig(throttling_default_max=0, throttling_default_per_seconds=60)

    @pytest.mark.asyncio
    async def test_edge_case_negative_limit(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test handling with negative rate limit."""
        from aiogram_sentinel.config import SentinelConfig
        from aiogram_sentinel.exceptions import ConfigurationError

        # Should raise configuration error for negative limit
        with pytest.raises(
            ConfigurationError, match="throttling_default_max must be positive"
        ):
            SentinelConfig(throttling_default_max=-1, throttling_default_per_seconds=60)

    @pytest.mark.asyncio
    async def test_edge_case_zero_window(
        self,
        mock_rate_limiter: Mock,
        mock_handler: Mock,
        mock_message: Mock,
        mock_data: dict[str, Any],
    ) -> None:
        """Test handling with zero window."""
        from aiogram_sentinel.config import SentinelConfig
        from aiogram_sentinel.exceptions import ConfigurationError

        # Should raise configuration error for zero window
        with pytest.raises(
            ConfigurationError, match="throttling_default_per_seconds must be positive"
        ):
            SentinelConfig(throttling_default_max=10, throttling_default_per_seconds=0)
