"""Tests for error handling middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Message, TelegramObject

from aiogram_sentinel.config import SentinelConfig
from aiogram_sentinel.exceptions import SentinelError
from aiogram_sentinel.middlewares.errors import ErrorConfig, ErrorHandlingMiddleware
from aiogram_sentinel.scopes import KeyBuilder
from aiogram_sentinel.storage.base import RateLimiterBackend


class TestErrorConfig:
    """Test ErrorConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = ErrorConfig()

        assert config.use_friendly_messages is True
        assert config.domain_classifier is None
        assert config.message_resolver is None
        assert config.locale_resolver is None
        assert config.on_error is None
        assert config.sync_retry_after is True
        assert config.respond_strategy == "answer"
        assert config.show_alert_for_callbacks is False
        assert config.send_strategy is None

    def test_custom_config(self) -> None:
        """Test custom configuration values."""

        def domain_classifier(exc: Exception) -> str | None:
            return "custom_error"

        def message_resolver(key: str, locale: str) -> str:
            return f"{key}_{locale}"

        def locale_resolver(event: TelegramObject, data: dict) -> str:
            return "fr"

        async def on_error(event: TelegramObject, exc: Exception, data: dict) -> None:
            pass

        config = ErrorConfig(
            use_friendly_messages=False,
            domain_classifier=domain_classifier,
            message_resolver=message_resolver,
            locale_resolver=locale_resolver,
            on_error=on_error,
            sync_retry_after=False,
            respond_strategy="reply",
            show_alert_for_callbacks=True,
        )

        assert config.use_friendly_messages is False
        assert config.domain_classifier is domain_classifier
        assert config.message_resolver is message_resolver
        assert config.locale_resolver is locale_resolver
        assert config.on_error is on_error
        assert config.sync_retry_after is False
        assert config.respond_strategy == "reply"
        assert config.show_alert_for_callbacks is True


class TestErrorHandlingMiddleware:
    """Test ErrorHandlingMiddleware."""

    @pytest.fixture
    def config(self) -> SentinelConfig:
        """Create test configuration."""
        return SentinelConfig(backend="memory")

    @pytest.fixture
    def key_builder(self) -> KeyBuilder:
        """Create test key builder."""
        return KeyBuilder(app="test")

    @pytest.fixture
    def rate_limiter(self) -> AsyncMock:
        """Create mock rate limiter."""
        return AsyncMock(spec=RateLimiterBackend)

    @pytest.fixture
    def middleware(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> ErrorHandlingMiddleware:
        """Create test middleware."""
        config = ErrorConfig()
        return ErrorHandlingMiddleware(config, key_builder, rate_limiter)

    @pytest.fixture
    def mock_event(self) -> TelegramObject:
        """Create mock event."""
        event = MagicMock(spec=TelegramObject)
        event.from_user = MagicMock()
        event.from_user.id = 123
        event.chat = MagicMock()
        event.chat.id = 456
        return event

    @pytest.fixture
    def mock_data(self) -> dict:
        """Create mock data."""
        return {"test": "data"}

    def test_init(self, key_builder: KeyBuilder, rate_limiter: AsyncMock) -> None:
        """Test middleware initialization."""
        config = ErrorConfig()
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        assert middleware._cfg is config
        assert middleware._key_builder is key_builder
        assert middleware._rate_limiter is rate_limiter

    @pytest.mark.asyncio
    async def test_call_success(
        self,
        middleware: ErrorHandlingMiddleware,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test successful handler execution."""
        handler = AsyncMock(return_value="success")

        result = await middleware(handler, mock_event, mock_data)

        assert result == "success"
        handler.assert_called_once_with(mock_event, mock_data)

    @pytest.mark.asyncio
    async def test_call_with_exception(
        self,
        middleware: ErrorHandlingMiddleware,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test handler execution with exception."""
        handler = AsyncMock(side_effect=ValueError("test error"))

        with patch.object(middleware, "_handle_error") as mock_handle:
            result = await middleware(handler, mock_event, mock_data)

            assert result is None
            mock_handle.assert_called_once()

    def test_classify_exception_telegram(
        self, middleware: ErrorHandlingMiddleware
    ) -> None:
        """Test Telegram exception classification."""
        # Create mock exceptions with proper parameters
        bad_request = TelegramBadRequest(
            method=SendMessage(chat_id=123, text="test"), message="bad request"
        )
        forbidden = TelegramForbiddenError(
            method=SendMessage(chat_id=123, text="test"), message="forbidden"
        )
        retry_after = TelegramRetryAfter(
            method=SendMessage(chat_id=123, text="test"),
            message="retry after",
            retry_after=5,
        )
        api_error = TelegramAPIError(
            method=SendMessage(chat_id=123, text="test"), message="generic"
        )

        assert (
            middleware._classify_exception(bad_request) == "error_telegram_badrequest"
        )
        assert middleware._classify_exception(forbidden) == "error_telegram_forbidden"
        assert (
            middleware._classify_exception(retry_after) == "error_telegram_retry_after"
        )
        assert middleware._classify_exception(api_error) == "error_telegram_generic"

    def test_classify_exception_sentinel(
        self, middleware: ErrorHandlingMiddleware
    ) -> None:
        """Test Sentinel exception classification."""
        assert (
            middleware._classify_exception(SentinelError("sentinel error"))
            == "error_sentinel_generic"
        )

    def test_classify_exception_domain(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test domain exception classification."""

        def domain_classifier(exc: Exception) -> str | None:
            if isinstance(exc, ValueError):
                return "error_validation"
            return None

        config = ErrorConfig(domain_classifier=domain_classifier)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        assert (
            middleware._classify_exception(ValueError("validation error"))
            == "error_validation"
        )
        assert (
            middleware._classify_exception(RuntimeError("runtime error"))
            == "error_unexpected_system"
        )

    def test_classify_exception_domain_failure(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test domain classifier failure handling."""

        def domain_classifier(exc: Exception) -> str | None:
            raise Exception("classifier error")

        config = ErrorConfig(domain_classifier=domain_classifier)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        # Should fallback to system error
        assert (
            middleware._classify_exception(ValueError("test"))
            == "error_unexpected_system"
        )

    def test_resolve_locale_default(
        self,
        middleware: ErrorHandlingMiddleware,
        mock_event: TelegramObject,
        mock_data: dict,
    ) -> None:
        """Test default locale resolution."""
        locale = middleware._resolve_locale(mock_event, mock_data)
        assert locale == "en"

    def test_resolve_locale_custom(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test custom locale resolution."""

        def locale_resolver(event: TelegramObject, data: dict) -> str:
            return "fr"

        config = ErrorConfig(locale_resolver=locale_resolver)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        mock_event = MagicMock()
        mock_data = {}

        locale = middleware._resolve_locale(mock_event, mock_data)
        assert locale == "fr"

    def test_resolve_locale_failure(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test locale resolver failure handling."""

        def locale_resolver(event: TelegramObject, data: dict) -> str:
            raise Exception("resolver error")

        config = ErrorConfig(locale_resolver=locale_resolver)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        mock_event = MagicMock()
        mock_data = {}

        # Should fallback to default
        locale = middleware._resolve_locale(mock_event, mock_data)
        assert locale == "en"

    def test_resolve_message_default(self, middleware: ErrorHandlingMiddleware) -> None:
        """Test default message resolution."""
        message = middleware._resolve_message("error_test", "en")
        assert message == "error_test"

    def test_resolve_message_custom(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test custom message resolution."""

        def message_resolver(key: str, locale: str) -> str:
            return f"{key}_{locale}"

        config = ErrorConfig(message_resolver=message_resolver)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        message = middleware._resolve_message("error_test", "en")
        assert message == "error_test_en"

    def test_resolve_message_failure(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test message resolver failure handling."""

        def message_resolver(key: str, locale: str) -> str:
            raise Exception("resolver error")

        config = ErrorConfig(message_resolver=message_resolver)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        # Should fallback to key
        message = middleware._resolve_message("error_test", "en")
        assert message == "error_test"

    @pytest.mark.asyncio
    async def test_sync_retry_after(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test RetryAfter synchronization."""
        config = ErrorConfig(sync_retry_after=True)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        exc = TelegramRetryAfter(
            method=SendMessage(chat_id=123, text="test"),
            message="retry after",
            retry_after=5,
        )

        await middleware._sync_retry_after(exc, 123, 456)

        # Should call rate limiter with ceil of retry_after
        rate_limiter.allow.assert_called_once()
        call_args = rate_limiter.allow.call_args
        assert call_args[0][1] == 1  # limit
        assert call_args[0][2] == 5  # ceil(5) = 5

    @pytest.mark.asyncio
    async def test_sync_retry_after_disabled(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test RetryAfter synchronization when disabled."""
        config = ErrorConfig(sync_retry_after=False)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        # Create mock event and data
        event = MagicMock()
        event.from_user = MagicMock()
        event.from_user.id = 123
        event.chat = MagicMock()
        event.chat.id = 456
        event.__class__.__name__ = "Message"
        data = {}

        # Create handler that raises RetryAfter
        async def failing_handler(event, data):
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=123, text="test"),
                message="retry after",
                retry_after=5,
            )

        # Execute middleware
        await middleware(failing_handler, event, data)

        # Should not call rate limiter
        rate_limiter.allow.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_retry_after_no_rate_limiter(
        self, key_builder: KeyBuilder
    ) -> None:
        """Test RetryAfter synchronization without rate limiter."""
        config = ErrorConfig(sync_retry_after=True)
        middleware = ErrorHandlingMiddleware(config, key_builder, None)

        exc = TelegramRetryAfter(
            method=SendMessage(chat_id=123, text="test"),
            message="retry after",
            retry_after=5,
        )

        # Should not raise
        await middleware._sync_retry_after(exc, 123, 456)

    @pytest.mark.asyncio
    async def test_sync_retry_after_failure(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test RetryAfter synchronization failure handling."""
        config = ErrorConfig(sync_retry_after=True)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        rate_limiter.allow.side_effect = Exception("rate limiter error")

        exc = TelegramRetryAfter(
            method=SendMessage(chat_id=123, text="test"),
            message="retry after",
            retry_after=5,
        )

        # Should not raise
        await middleware._sync_retry_after(exc, 123, 456)

    @pytest.mark.asyncio
    async def test_default_send_strategy_callback(
        self, middleware: ErrorHandlingMiddleware
    ) -> None:
        """Test default send strategy for callback query."""
        callback = AsyncMock(spec=CallbackQuery)
        data = {}

        await middleware._default_send_strategy(callback, data, "test message")

        callback.answer.assert_called_once_with("test message", show_alert=False)

    @pytest.mark.asyncio
    async def test_default_send_strategy_callback_with_alert(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test default send strategy for callback query with alert."""
        config = ErrorConfig(show_alert_for_callbacks=True)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        callback = AsyncMock(spec=CallbackQuery)
        data = {}

        await middleware._default_send_strategy(callback, data, "test message")

        callback.answer.assert_called_once_with("test message", show_alert=True)

    @pytest.mark.asyncio
    async def test_default_send_strategy_message(
        self, middleware: ErrorHandlingMiddleware
    ) -> None:
        """Test default send strategy for message."""
        message = AsyncMock(spec=Message)
        data = {"message": message}

        await middleware._default_send_strategy(MagicMock(), data, "test message")

        message.reply.assert_called_once_with("test message", disable_notification=True)

    @pytest.mark.asyncio
    async def test_default_send_strategy_message_direct(
        self, middleware: ErrorHandlingMiddleware
    ) -> None:
        """Test default send strategy for message event directly."""
        message = AsyncMock(spec=Message)
        data = {}

        await middleware._default_send_strategy(message, data, "test message")

        message.reply.assert_called_once_with("test message", disable_notification=True)

    @pytest.mark.asyncio
    async def test_default_send_strategy_no_target(
        self, middleware: ErrorHandlingMiddleware
    ) -> None:
        """Test default send strategy with no suitable target."""
        event = MagicMock()
        data = {}

        # Should not raise
        await middleware._default_send_strategy(event, data, "test message")

    @pytest.mark.asyncio
    async def test_default_send_strategy_send_failure(
        self, middleware: ErrorHandlingMiddleware
    ) -> None:
        """Test default send strategy with send failure."""
        message = AsyncMock(spec=Message)
        message.reply.side_effect = Exception("send failed")
        data = {"message": message}

        # Should not raise
        await middleware._default_send_strategy(MagicMock(), data, "test message")

    @pytest.mark.asyncio
    async def test_send_friendly_message_custom_strategy(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test sending friendly message with custom strategy."""
        custom_strategy = AsyncMock()
        config = ErrorConfig(send_strategy=custom_strategy)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        event = MagicMock()
        data = {}

        await middleware._send_friendly_message("error_test", "en", event, data)

        custom_strategy.assert_called_once_with(event, data, "error_test")

    @pytest.mark.asyncio
    async def test_send_friendly_message_custom_strategy_failure(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test sending friendly message with custom strategy failure."""
        custom_strategy = AsyncMock(side_effect=Exception("strategy failed"))
        config = ErrorConfig(send_strategy=custom_strategy)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        event = MagicMock()
        data = {}

        # Should fallback to default strategy
        with patch.object(middleware, "_default_send_strategy") as mock_default:
            await middleware._send_friendly_message("error_test", "en", event, data)
            mock_default.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_error_hook(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test on_error hook execution."""
        on_error = AsyncMock()
        config = ErrorConfig(on_error=on_error)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        event = MagicMock()
        data = {}
        exc = ValueError("test error")

        await middleware._handle_error(exc, event, data)

        on_error.assert_called_once_with(event, exc, data)

    @pytest.mark.asyncio
    async def test_on_error_hook_failure(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test on_error hook failure handling."""
        on_error = AsyncMock(side_effect=Exception("hook failed"))
        config = ErrorConfig(on_error=on_error)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        event = MagicMock()
        data = {}
        exc = ValueError("test error")

        # Should not raise
        await middleware._handle_error(exc, event, data)

        on_error.assert_called_once_with(event, exc, data)

    @pytest.mark.asyncio
    async def test_handle_error_full_flow(
        self, key_builder: KeyBuilder, rate_limiter: AsyncMock
    ) -> None:
        """Test full error handling flow."""
        on_error = AsyncMock()
        config = ErrorConfig(on_error=on_error, use_friendly_messages=True)
        middleware = ErrorHandlingMiddleware(config, key_builder, rate_limiter)

        event = MagicMock()
        event.from_user = MagicMock()
        event.from_user.id = 123
        event.chat = MagicMock()
        event.chat.id = 456
        data = {}
        exc = ValueError("test error")

        with patch.object(middleware, "_send_friendly_message") as mock_send:
            await middleware._handle_error(exc, event, data)

            mock_send.assert_called_once()
            on_error.assert_called_once_with(event, exc, data)
