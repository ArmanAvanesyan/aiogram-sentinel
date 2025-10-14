"""Debouncing middleware for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..config import SentinelConfig
from ..context import extract_group_ids, extract_handler_bucket
from ..scopes import KeyBuilder
from ..storage.base import DebounceBackend
from ..utils.keys import fingerprint


class DebounceMiddleware(BaseMiddleware):
    """Middleware for debouncing duplicate messages with fingerprinting."""

    def __init__(
        self,
        debounce_backend: DebounceBackend,
        cfg: SentinelConfig,
        key_builder: KeyBuilder,
    ) -> None:
        """Initialize the debouncing middleware.

        Args:
            debounce_backend: Debounce backend instance
            cfg: SentinelConfig configuration
            key_builder: KeyBuilder instance for key generation
        """
        super().__init__()
        self._debounce_backend = debounce_backend
        self._cfg = cfg
        self._key_builder = key_builder
        self._default_delay = cfg.debounce_default_window

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
        fp = self._generate_fingerprint(event)

        # Generate debounce key
        key = self._generate_debounce_key(event, handler, data)

        # Check if already seen within window
        if await self._debounce_backend.seen(key, window_seconds, fp):
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
            if isinstance(config, (tuple, list)) and len(config) >= 1:  # type: ignore
                return int(config[0])  # type: ignore
            elif isinstance(config, dict):
                delay = config.get("delay", self._cfg.debounce_default_window)  # type: ignore
                return int(delay)  # type: ignore

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
        """Generate debounce key for the event using KeyBuilder."""
        # Extract user and chat IDs using context extractors
        user_id, chat_id = extract_group_ids(event, data)

        # Auto-extract bucket from handler
        bucket = extract_handler_bucket(event, data)

        # Get handler name as fallback bucket
        if bucket is None:
            bucket = getattr(handler, "__name__", "unknown")

        # Get additional parameters from handler config or data
        method = None
        explicit_bucket = None

        # Check handler configuration for overrides
        if hasattr(handler, "sentinel_debounce"):
            config = handler.sentinel_debounce  # type: ignore
            if isinstance(config, dict):
                method = config.get("method")  # type: ignore
                explicit_bucket = config.get("bucket")  # type: ignore

        # Check data for overrides
        if "sentinel_method" in data:
            method = data["sentinel_method"]
        if "sentinel_bucket" in data:
            explicit_bucket = data["sentinel_bucket"]

        # Use explicit bucket if provided, otherwise use auto-extracted
        final_bucket = explicit_bucket if explicit_bucket is not None else bucket

        # Determine scope and build key
        if user_id is not None and chat_id is not None:
            # Both user and chat available - use GROUP scope
            return self._key_builder.group(
                "debounce", user_id, chat_id, method=method, bucket=final_bucket
            )
        elif user_id is not None:
            # Only user available - use USER scope
            return self._key_builder.user(
                "debounce", user_id, method=method, bucket=final_bucket
            )
        elif chat_id is not None:
            # Only chat available - use CHAT scope
            return self._key_builder.chat(
                "debounce", chat_id, method=method, bucket=final_bucket
            )
        else:
            # Neither available - use GLOBAL scope
            return self._key_builder.global_(
                "debounce", method=method, bucket=final_bucket
            )
