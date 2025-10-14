"""Integration tests for error handling."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, TelegramObject

from aiogram_sentinel.config import SentinelConfig
from aiogram_sentinel.events import BaseEvent, ErrorEvent, events
from aiogram_sentinel.middlewares.errors import ErrorConfig, ErrorHandlingMiddleware
from aiogram_sentinel.scopes import KeyBuilder
from aiogram_sentinel.storage.memory import MemoryRateLimiter


class TestErrorIntegration:
    """Integration tests for error handling."""

    @pytest.fixture
    def config(self) -> SentinelConfig:
        """Create test configuration."""
        return SentinelConfig(backend="memory")

    @pytest.fixture
    def key_builder(self) -> KeyBuilder:
        """Create test key builder."""
        return KeyBuilder(app="test")

    @pytest.fixture
    def rate_limiter(self) -> MemoryRateLimiter:
        """Create memory rate limiter."""
        return MemoryRateLimiter()

    @pytest.fixture
    def middleware(
        self, key_builder: KeyBuilder, rate_limiter: MemoryRateLimiter
    ) -> ErrorHandlingMiddleware:
        """Create test middleware."""
        config = ErrorConfig(sync_retry_after=True)
        return ErrorHandlingMiddleware(config, key_builder, rate_limiter)

    @pytest.fixture
    def mock_event(self) -> TelegramObject:
        """Create mock event."""
        event = MagicMock(spec=TelegramObject)
        event.from_user = MagicMock()
        event.from_user.id = 123
        event.chat = MagicMock()
        event.chat.id = 456
        event.__class__.__name__ = "Message"
        return event

    @pytest.fixture
    def mock_data(self) -> dict:
        """Create mock data."""
        return {"test": "data"}

    @pytest.mark.asyncio
    async def test_retry_after_sync_integration(
        self,
        middleware: ErrorHandlingMiddleware,
        rate_limiter: MemoryRateLimiter,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test RetryAfter synchronization with real rate limiter."""

        # Create a handler that raises RetryAfter
        async def failing_handler(event: TelegramObject, data: dict) -> None:
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=123, text="test"),
                message="retry after",
                retry_after=5,
            )

        # Execute the middleware
        result = await middleware(failing_handler, mock_event, mock_data)

        # Should return None (error handled)
        assert result is None

        # Check that a cooldown was set in the rate limiter
        # The key should be generated for the retryafter namespace
        # We can't easily check the exact key, but we can verify the rate limiter
        # has some data (indicating the cooldown was set)
        assert len(rate_limiter._counters) > 0

    @pytest.mark.asyncio
    async def test_error_event_emission(
        self,
        middleware: ErrorHandlingMiddleware,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test that ErrorEvent is emitted to the event bus."""
        captured_events = []

        async def event_handler(event: BaseEvent) -> None:
            if isinstance(event, ErrorEvent):
                captured_events.append(event)

        # Subscribe to error events
        events.subscribe(ErrorEvent, event_handler)

        # Create a handler that raises an exception
        async def failing_handler(event: TelegramObject, data: dict) -> None:
            raise ValueError("test error")

        # Execute the middleware
        await middleware(failing_handler, mock_event, mock_data)

        # Give event processing time to complete
        await asyncio.sleep(0.01)

        # Check that an error event was captured
        assert len(captured_events) == 1
        event = captured_events[0]
        assert event.error_type == "error_unexpected_system"
        assert event.error_message == "test error"
        assert event.event_type == "message"
        assert event.user_id == 123
        assert event.chat_id == 456
        assert event.locale == "en"

    @pytest.mark.asyncio
    async def test_telegram_exception_classification(
        self,
        middleware: ErrorHandlingMiddleware,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test Telegram exception classification in full flow."""
        captured_events = []

        async def event_handler(event: BaseEvent) -> None:
            if isinstance(event, ErrorEvent):
                captured_events.append(event)

        events.subscribe(ErrorEvent, event_handler)

        # Test different Telegram exceptions
        test_cases = [
            (
                TelegramRetryAfter(
                    method=SendMessage(chat_id=123, text="test"),
                    message="retry after",
                    retry_after=5,
                ),
                "error_telegram_retry_after",
            ),
        ]

        for exc, expected_type in test_cases:
            captured_events.clear()

            async def failing_handler(event: TelegramObject, data: dict) -> None:
                raise exc  # noqa: B023

            await middleware(failing_handler, mock_event, mock_data)
            await asyncio.sleep(0.01)

            assert len(captured_events) == 1
            assert captured_events[0].error_type == expected_type

    @pytest.mark.asyncio
    async def test_domain_classifier_integration(
        self,
        key_builder: KeyBuilder,
        rate_limiter: MemoryRateLimiter,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test domain classifier integration."""

        def domain_classifier(exc: Exception) -> str | None:
            if isinstance(exc, ValueError):
                return "error_validation"
            elif isinstance(exc, RuntimeError):
                return "error_runtime"
            return None

        config = ErrorConfig(domain_classifier=domain_classifier)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        captured_events = []

        async def event_handler(event: BaseEvent) -> None:
            if isinstance(event, ErrorEvent):
                captured_events.append(event)

        events.subscribe(ErrorEvent, event_handler)

        # Test domain classification
        async def failing_handler(event: TelegramObject, data: dict) -> None:
            raise ValueError("validation error")

        await middleware(failing_handler, mock_event, mock_data)
        await asyncio.sleep(0.01)

        assert len(captured_events) == 1
        assert captured_events[0].error_type == "error_validation"

    @pytest.mark.asyncio
    async def test_locale_resolver_integration(
        self,
        key_builder: KeyBuilder,
        rate_limiter: MemoryRateLimiter,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test locale resolver integration."""

        def locale_resolver(event: TelegramObject, data: dict) -> str:
            # Simulate getting locale from user data
            return "fr"

        config = ErrorConfig(locale_resolver=locale_resolver)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        captured_events = []

        async def event_handler(event: BaseEvent) -> None:
            if isinstance(event, ErrorEvent):
                captured_events.append(event)

        events.subscribe(ErrorEvent, event_handler)

        async def failing_handler(event: TelegramObject, data: dict) -> None:
            raise ValueError("test error")

        await middleware(failing_handler, mock_event, mock_data)
        await asyncio.sleep(0.01)

        assert len(captured_events) == 1
        assert captured_events[0].locale == "fr"

    @pytest.mark.asyncio
    async def test_message_sending_integration(
        self,
        key_builder: KeyBuilder,
        rate_limiter: MemoryRateLimiter,
    ) -> None:
        """Test message sending integration."""
        config = ErrorConfig(use_friendly_messages=True)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        # Test callback query
        callback = AsyncMock(spec=CallbackQuery)
        callback.from_user = MagicMock()
        callback.from_user.id = 123
        callback.chat = MagicMock()
        callback.chat.id = 456
        callback.__class__.__name__ = "CallbackQuery"

        async def failing_handler(event: TelegramObject, data: dict) -> None:
            raise ValueError("test error")

        await middleware(failing_handler, callback, {})

        # Should have called answer on the callback
        callback.answer.assert_called_once()
        call_args = callback.answer.call_args
        assert call_args[0][0] == "error_unexpected_system"  # Default message
        assert call_args[1]["show_alert"] is False  # Default alert setting

    @pytest.mark.asyncio
    async def test_on_error_hook_integration(
        self,
        key_builder: KeyBuilder,
        rate_limiter: MemoryRateLimiter,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test on_error hook integration."""
        on_error_called = False
        captured_exc = None
        captured_event = None
        captured_data = None

        async def on_error(event: TelegramObject, exc: Exception, data: dict) -> None:
            nonlocal on_error_called, captured_exc, captured_event, captured_data
            on_error_called = True
            captured_exc = exc
            captured_event = event
            captured_data = data

        config = ErrorConfig(on_error=on_error)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        test_exc = ValueError("test error")

        async def failing_handler(event: TelegramObject, data: dict) -> None:
            raise test_exc

        await middleware(failing_handler, mock_event, mock_data)

        assert on_error_called is True
        assert captured_exc is test_exc
        assert captured_event is mock_event
        assert captured_data is mock_data

    @pytest.mark.asyncio
    async def test_error_handling_with_policy_middleware(
        self,
        key_builder: KeyBuilder,
        rate_limiter: MemoryRateLimiter,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test error handling works with policy middleware."""
        config = ErrorConfig()
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        # Simulate policy middleware data
        mock_data["sentinel_throttle_cfg"] = MagicMock()

        captured_events = []

        async def event_handler(event: BaseEvent) -> None:
            if isinstance(event, ErrorEvent):
                captured_events.append(event)

        events.subscribe(ErrorEvent, event_handler)

        async def failing_handler(event: TelegramObject, data: dict) -> None:
            raise ValueError("test error")

        await middleware(failing_handler, mock_event, mock_data)
        await asyncio.sleep(0.01)

        # Should still handle the error correctly
        assert len(captured_events) == 1
        assert captured_events[0].error_type == "error_unexpected_system"

    @pytest.mark.asyncio
    async def test_error_handling_resilience(
        self,
        key_builder: KeyBuilder,
        rate_limiter: MemoryRateLimiter,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test error handling resilience - middleware should never crash."""

        # Create a middleware with failing components
        def failing_locale_resolver(event: TelegramObject, data: dict) -> str:
            raise Exception("locale resolver failed")

        def failing_message_resolver(key: str, locale: str) -> str:
            raise Exception("message resolver failed")

        async def failing_on_error(
            event: TelegramObject, exc: Exception, data: dict
        ) -> None:
            raise Exception("on_error failed")

        config = ErrorConfig(
            locale_resolver=failing_locale_resolver,
            message_resolver=failing_message_resolver,
            on_error=failing_on_error,
            use_friendly_messages=True,
        )
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        # Mock message sending to fail
        with patch.object(
            middleware, "_default_send_strategy", side_effect=Exception("send failed")
        ):

            async def failing_handler(event: TelegramObject, data: dict) -> None:
                raise ValueError("test error")

            # Should not raise despite all components failing
            result = await middleware(failing_handler, mock_event, mock_data)
            assert result is None
