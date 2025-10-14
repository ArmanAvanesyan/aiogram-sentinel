"""Error handling middleware for aiogram-sentinel."""

from __future__ import annotations

import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramConflictError,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.types import CallbackQuery, Message, TelegramObject

from ..context import extract_event_type, extract_group_ids
from ..events import ErrorEvent, events
from ..exceptions import SentinelError
from ..policy import resolve_scope
from ..scopes import KeyBuilder, Scope
from ..storage.base import RateLimiterBackend

logger = logging.getLogger(__name__)


@dataclass
class ErrorConfig:
    """Configuration for error handling middleware."""

    use_friendly_messages: bool = True
    domain_classifier: Callable[[Exception], str | None] | None = None
    message_resolver: Callable[[str, str], str] | None = None
    locale_resolver: Callable[[TelegramObject, dict[str, Any]], str] | None = None
    on_error: (
        Callable[[TelegramObject, Exception, dict[str, Any]], Awaitable[None]] | None
    ) = None
    sync_retry_after: bool = True
    respond_strategy: str = "answer"  # "answer", "reply", "none"
    show_alert_for_callbacks: bool = False
    send_strategy: (
        Callable[[TelegramObject, dict[str, Any], str], Awaitable[None]] | None
    ) = None


class ErrorHandlingMiddleware(BaseMiddleware):
    """Middleware for centralized error handling."""

    def __init__(
        self,
        cfg: ErrorConfig,
        key_builder: KeyBuilder,
        rate_limiter: RateLimiterBackend | None = None,
    ) -> None:
        """Initialize the error handling middleware.

        Args:
            cfg: Error configuration
            key_builder: KeyBuilder instance for key generation
            rate_limiter: Optional rate limiter for RetryAfter sync
        """
        super().__init__()
        self._cfg = cfg
        self._key_builder = key_builder
        self._rate_limiter = rate_limiter

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process the event through error handling middleware."""
        try:
            return await handler(event, data)
        except Exception as exc:
            await self._handle_error(exc, event, data)
            # Don't re-raise - error has been handled
            return None

    async def _handle_error(
        self,
        exc: Exception,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> None:
        """Handle an exception that occurred during processing.

        Args:
            exc: The exception that occurred
            event: Telegram event object
            data: Middleware data dictionary
        """
        # Classify the exception
        error_key = self._classify_exception(exc)

        # Resolve locale
        locale = self._resolve_locale(event, data)

        # Build context
        user_id, chat_id = extract_group_ids(event, data)
        event_type = extract_event_type(event, data)

        # Extract retry_after if applicable
        retry_after = None
        if isinstance(exc, TelegramRetryAfter):
            retry_after = exc.retry_after

        # Publish error event
        error_event = ErrorEvent(
            error_type=error_key,
            error_message=str(exc),
            event_type=event_type,
            user_id=user_id,
            chat_id=chat_id,
            locale=locale,
            retry_after=retry_after,
        )
        events.publish(error_event)

        # Handle RetryAfter sync
        if (
            isinstance(exc, TelegramRetryAfter)
            and self._cfg.sync_retry_after
            and self._rate_limiter
        ):
            await self._sync_retry_after(exc, user_id, chat_id)

        # Send friendly message
        if self._cfg.use_friendly_messages:
            await self._send_friendly_message(error_key, locale, event, data)

        # Call on_error hook
        if self._cfg.on_error:
            try:
                await self._cfg.on_error(event, exc, data)
            except Exception as hook_exc:
                logger.exception("on_error hook failed: %s", hook_exc)

    def _classify_exception(self, exc: Exception) -> str:
        """Classify an exception to an i18n key.

        Args:
            exc: Exception to classify

        Returns:
            i18n key for the exception
        """
        # Check for Telegram API exceptions first
        if isinstance(exc, TelegramBadRequest):
            return "error_telegram_badrequest"
        elif isinstance(exc, TelegramForbiddenError):
            return "error_telegram_forbidden"
        elif isinstance(exc, TelegramConflictError):
            return "error_telegram_conflict"
        elif isinstance(exc, TelegramRetryAfter):
            return "error_telegram_retry_after"
        elif isinstance(exc, TelegramServerError):
            return "error_telegram_server"
        elif isinstance(exc, TelegramUnauthorizedError):
            return "error_telegram_unauthorized"
        elif isinstance(exc, TelegramAPIError):
            return "error_telegram_generic"

        # Check for aiogram-sentinel exceptions
        elif isinstance(exc, SentinelError):
            return "error_sentinel_generic"

        # Try domain classifier
        elif self._cfg.domain_classifier:
            try:
                domain_key = self._cfg.domain_classifier(exc)
                if domain_key:
                    return domain_key
            except Exception as e:
                logger.exception("Domain classifier failed: %s", e)

        # Fallback to system error
        return "error_unexpected_system"

    def _resolve_locale(
        self,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> str:
        """Resolve locale for the event.

        Args:
            event: Telegram event object
            data: Middleware data dictionary

        Returns:
            Locale string
        """
        if self._cfg.locale_resolver:
            try:
                return self._cfg.locale_resolver(event, data)
            except Exception as e:
                logger.exception("Locale resolver failed: %s", e)

        # Default fallback
        return "en"

    async def _sync_retry_after(
        self,
        exc: TelegramRetryAfter,
        user_id: int | None,
        chat_id: int | None,
    ) -> None:
        """Sync RetryAfter with internal cooldown.

        Args:
            exc: RetryAfter exception
            user_id: User ID
            chat_id: Chat ID
        """
        if not self._rate_limiter:
            return

        try:
            # Resolve scope for retry after key
            resolved_scope = resolve_scope(user_id, chat_id, None)
            if resolved_scope is None:
                resolved_scope = Scope.GLOBAL

            # Generate key
            if resolved_scope == Scope.GROUP and user_id and chat_id:
                key = self._key_builder.group("retryafter", user_id, chat_id)
            elif resolved_scope == Scope.USER and user_id:
                key = self._key_builder.user("retryafter", user_id)
            elif resolved_scope == Scope.CHAT and chat_id:
                key = self._key_builder.chat("retryafter", chat_id)
            else:
                key = self._key_builder.global_("retryafter")

            # Set TTL (ceil to ensure we don't under-estimate)
            ttl = math.ceil(exc.retry_after)

            # Use rate limiter to set the cooldown
            # We'll use a simple approach: set limit=1, window=ttl, and check if allowed
            # This effectively creates a cooldown
            await self._rate_limiter.allow(key, 1, ttl)

        except Exception as e:
            logger.exception("Failed to sync RetryAfter: %s", e)

    async def _send_friendly_message(
        self,
        error_key: str,
        locale: str,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> None:
        """Send a friendly error message to the user.

        Args:
            error_key: i18n key for the error
            locale: Locale for message resolution
            event: Telegram event object
            data: Middleware data dictionary
        """
        # Resolve message
        message_text = self._resolve_message(error_key, locale)

        # Use custom send strategy if provided
        if self._cfg.send_strategy:
            try:
                await self._cfg.send_strategy(event, data, message_text)
                return
            except Exception as e:
                logger.exception("Custom send strategy failed: %s", e)

        # Use default send strategy
        try:
            await self._default_send_strategy(event, data, message_text)
        except Exception as e:
            logger.exception("Failed to send friendly error message: %s", e)

    def _resolve_message(self, error_key: str, locale: str) -> str:
        """Resolve an error key to a localized message.

        Args:
            error_key: i18n key
            locale: Locale

        Returns:
            Localized message
        """
        if self._cfg.message_resolver:
            try:
                return self._cfg.message_resolver(error_key, locale)
            except Exception as e:
                logger.exception("Message resolver failed: %s", e)

        # Default fallback - return the key itself
        return error_key

    async def _default_send_strategy(
        self,
        event: TelegramObject,
        data: dict[str, Any],
        text: str,
    ) -> None:
        """Default message sending strategy.

        Args:
            event: Telegram event object
            data: Middleware data dictionary
            text: Message text to send
        """
        try:
            # Check if this is a callback query
            if isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=self._cfg.show_alert_for_callbacks)
                return

            # Check if we have a message in data
            message = data.get("message")
            if isinstance(message, Message):
                await message.reply(text, disable_notification=True)
                return

            # Check if event itself is a message
            if isinstance(event, Message):
                await event.reply(text, disable_notification=True)
                return

            # No suitable target found
            logger.debug("No suitable target found for error message")

        except Exception as e:
            # Check if it's a known Telegram exception that we should ignore
            if (
                "message not modified" in str(e).lower()
                or "can't initiate conversation" in str(e).lower()
            ):
                logger.debug("Could not send error message: %s", text)
            else:
                logger.exception("Failed to send friendly error message: %s", e)
