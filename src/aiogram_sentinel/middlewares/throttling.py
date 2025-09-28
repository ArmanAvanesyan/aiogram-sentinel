"""Throttling middleware for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..config import SentinelConfig
from ..storage.base import RateLimiterBackend
from ..utils.keys import rate_key


class ThrottlingMiddleware(BaseMiddleware):
    """Middleware for rate limiting with optional notifier hook."""

    def __init__(
        self,
        rate_limiter: RateLimiterBackend,
        cfg: SentinelConfig,
        on_rate_limited: Callable[
            [TelegramObject, dict[str, Any], float], Awaitable[None]
        ]
        | None = None,
    ) -> None:
        """Initialize the throttling middleware.

        Args:
            rate_limiter: Rate limiter backend instance
            cfg: SentinelConfig configuration
            on_rate_limited: Optional hook called when rate limit is exceeded
        """
        super().__init__()
        self._rate_limiter = rate_limiter
        self._cfg = cfg
        self._on_rate_limited = on_rate_limited

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process the event through throttling middleware."""
        # Get rate limit configuration from handler or use defaults
        max_events, per_seconds = self._get_rate_limit_config(handler, data)

        # Generate rate limit key
        key = self._generate_rate_limit_key(event, handler, data)

        # Check if request is allowed
        allowed = await self._rate_limiter.allow(key, max_events, per_seconds)

        if not allowed:
            # Rate limit exceeded
            data["sentinel_rate_limited"] = True

            # Calculate retry after time
            retry_after = self._calculate_retry_after(per_seconds)

            # Call optional hook
            if self._on_rate_limited:
                try:
                    await self._on_rate_limited(event, data, retry_after)
                except Exception:
                    # Log error but don't fail the middleware
                    pass

            # Stop processing
            return

        # Continue to next middleware/handler
        return await handler(event, data)

    def _get_rate_limit_config(
        self, handler: Callable[..., Any], data: dict[str, Any]
    ) -> tuple[int, int]:
        """Get rate limit configuration from handler or use defaults."""
        # Check if handler has rate limit configuration
        if hasattr(handler, "sentinel_rate_limit"):  # type: ignore
            config = handler.sentinel_rate_limit  # type: ignore
            max_events, per_seconds, _scope = config
            return max_events, per_seconds

        # Check data for rate limit configuration
        if "sentinel_rate_limit" in data:
            config = data["sentinel_rate_limit"]
            if isinstance(config, tuple) and len(config) >= 2:  # type: ignore
                return int(config[0]), int(config[1])  # type: ignore

        # Use defaults
        return (
            self._cfg.throttling_default_max,
            self._cfg.throttling_default_per_seconds,
        )

    def _generate_rate_limit_key(
        self, event: TelegramObject, handler: Callable[..., Any], data: dict[str, Any]
    ) -> str:
        """Generate rate limit key for the event."""
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

        return rate_key(user_id, handler_name, **scope_kwargs)

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

    def _calculate_retry_after(self, window: int) -> float:
        """Calculate retry after time in seconds."""
        # Simple implementation - return the window duration
        # In a real implementation, this could be more sophisticated
        return float(window)


def rate_limit(
    limit: int = 10, window: int = 60
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to set rate limit configuration on handlers.

    Args:
        limit: Maximum number of requests per window
        window: Time window in seconds
    """

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        # Store rate limit configuration on the handler
        handler._sentinel_rate_limit = {"limit": limit, "window": window}  # type: ignore
        return handler

    return decorator
