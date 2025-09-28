"""Debouncing middleware for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..config import SentinelConfig
from ..storage.base import DebounceBackend
from ..utils.keys import debounce_key, fingerprint


class DebounceMiddleware(BaseMiddleware):
    """Middleware for debouncing duplicate messages with fingerprinting."""

    def __init__(
        self,
        debounce_backend: DebounceBackend,
        cfg: SentinelConfig,
    ) -> None:
        """Initialize the debouncing middleware.

        Args:
            debounce_backend: Debounce backend instance
            cfg: SentinelConfig configuration
        """
        super().__init__()
        self._debounce_backend = debounce_backend
        self._cfg = cfg

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process the event through debouncing middleware."""
        # Get debounce configuration
        window_seconds = self._get_debounce_window(handler, data)

        # Generate fingerprint for the event
        fingerprint = self._generate_fingerprint(event)

        # Generate debounce key
        key = self._generate_debounce_key(event, handler, data)

        # Check if already seen within window
        if await self._debounce_backend.seen(key, window_seconds, fingerprint):
            # Duplicate detected within window
            data["sentinel_debounced"] = True
            return  # Stop processing

        # Continue to next middleware/handler
        return await handler(event, data)

    def _get_debounce_window(
        self, handler: Callable[..., Any], data: dict[str, Any]
    ) -> int:
        """Get debounce window from handler or use default."""
        # Check if handler has debounce configuration
        if hasattr(handler, "sentinel_debounce"):  # type: ignore
            config = handler.sentinel_debounce  # type: ignore
            window_seconds, _scope = config
            return window_seconds

        # Check data for debounce configuration
        if "sentinel_debounce" in data:
            config = data["sentinel_debounce"]
            if isinstance(config, tuple) and len(config) >= 1:  # type: ignore
                return int(config[0])  # type: ignore

        # Use default
        return self._cfg.debounce_default_window

    def _generate_fingerprint(self, event: TelegramObject) -> str:
        """Generate SHA256 fingerprint for event content."""
        content = self._extract_content(event)

        if not content:
            # Fallback to hashed representation of the entire event
            content = str(event)

        return fingerprint(content)

    def _extract_content(self, event: TelegramObject) -> str:
        """Extract content from event for fingerprinting."""
        # Try to get text from message
        if hasattr(event, "text") and getattr(event, "text", None):  # type: ignore
            return event.text  # type: ignore

        # Try to get caption from message
        if hasattr(event, "caption") and getattr(event, "caption", None):  # type: ignore
            return event.caption  # type: ignore

        # Try to get data from callback query
        if hasattr(event, "data") and getattr(event, "data", None):  # type: ignore
            return event.data  # type: ignore

        # Try to get query from inline query
        if hasattr(event, "query") and getattr(event, "query", None):  # type: ignore
            return event.query  # type: ignore

        # Return empty string if no content found
        return ""

    def _generate_debounce_key(
        self,
        event: TelegramObject,
        handler: Callable[..., Any],
        data: dict[str, Any],
    ) -> str:
        """Generate debounce key for the event."""
        # Extract user ID
        user_id = self._extract_user_id(event)

        # Get handler name
        handler_name = getattr(handler, "__name__", "unknown")  # type: ignore

        # Get additional scope from data
        scope_kwargs = {}
        if "chat_id" in data:
            scope_kwargs["chat_id"] = data["chat_id"]
        if "message_id" in data:
            scope_kwargs["message_id"] = data["message_id"]

        return debounce_key(user_id, handler_name, **scope_kwargs)

    def _extract_user_id(self, event: TelegramObject) -> int:
        """Extract user ID from event."""
        # Try different event types
        if hasattr(event, "from_user") and getattr(event, "from_user", None):  # type: ignore
            return getattr(event.from_user, "id", 0)  # type: ignore
        elif hasattr(event, "user") and getattr(event, "user", None):  # type: ignore
            return getattr(event.user, "id", 0)  # type: ignore
        elif hasattr(event, "chat") and getattr(event, "chat", None):  # type: ignore
            return getattr(event.chat, "id", 0)  # type: ignore
        else:
            # Fallback to 0 for anonymous events
            return 0


def debounce(delay: float = 1.0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to set debounce configuration on handlers.

    Args:
        delay: Debounce delay in seconds
    """

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        # Store debounce configuration on the handler
        handler._sentinel_debounce = {"delay": delay}  # type: ignore
        return handler

    return decorator
