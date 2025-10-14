"""Throttling middleware for aiogram-sentinel."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..config import SentinelConfig
from ..context import extract_group_ids, extract_handler_bucket
from ..scopes import KeyBuilder
from ..storage.base import RateLimiterBackend

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """Middleware for rate limiting with optional notifier hook."""

    def __init__(
        self,
        rate_limiter: RateLimiterBackend,
        cfg: SentinelConfig,
        key_builder: KeyBuilder,
        on_rate_limited: Callable[
            [TelegramObject, dict[str, Any], float], Awaitable[None]
        ]
        | None = None,
    ) -> None:
        """Initialize the throttling middleware.

        Args:
            rate_limiter: Rate limiter backend instance
            cfg: SentinelConfig configuration
            key_builder: KeyBuilder instance for key generation
            on_rate_limited: Optional hook called when rate limit is exceeded
        """
        super().__init__()
        self._rate_limiter = rate_limiter
        self._cfg = cfg
        self._key_builder = key_builder
        self._on_rate_limited = on_rate_limited
        self._default_limit = cfg.throttling_default_max
        self._default_window = cfg.throttling_default_per_seconds

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

            # Calculate retry after time using actual remaining TTL
            retry_after = await self._calculate_retry_after(key, per_seconds)

            # Call optional hook
            if self._on_rate_limited:
                try:
                    await self._on_rate_limited(event, data, retry_after)
                except Exception as e:
                    logger.exception("on_rate_limited hook failed: %s", e)

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
            if isinstance(config, (tuple, list)) and len(config) >= 2:  # type: ignore
                return int(config[0]), int(config[1])  # type: ignore
            elif isinstance(config, dict):
                limit = config.get("limit", self._cfg.throttling_default_max)  # type: ignore
                window = config.get("window", self._cfg.throttling_default_per_seconds)  # type: ignore
                return int(limit), int(window)  # type: ignore

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
        """Generate rate limit key for the event using KeyBuilder."""
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
        if hasattr(handler, "sentinel_rate_limit"):
            config = handler.sentinel_rate_limit  # type: ignore
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
                "throttle", user_id, chat_id, method=method, bucket=final_bucket
            )
        elif user_id is not None:
            # Only user available - use USER scope
            return self._key_builder.user(
                "throttle", user_id, method=method, bucket=final_bucket
            )
        elif chat_id is not None:
            # Only chat available - use CHAT scope
            return self._key_builder.chat(
                "throttle", chat_id, method=method, bucket=final_bucket
            )
        else:
            # Neither available - use GLOBAL scope
            return self._key_builder.global_(
                "throttle", method=method, bucket=final_bucket
            )

    async def _calculate_retry_after(self, key: str, window: int) -> float:
        """Calculate retry after time in seconds using actual remaining TTL."""
        # Get remaining requests to calculate when the window will reset
        remaining = await self._rate_limiter.get_remaining(key, 1, window)

        # If no remaining requests, calculate time until oldest request expires
        if remaining == 0:
            # For memory backend, we need to check the actual timestamps
            # For Redis backend, we can use TTL
            if hasattr(self._rate_limiter, "_redis"):
                # Redis backend - use TTL
                try:
                    ttl = await self._rate_limiter._redis.ttl(key)  # type: ignore
                    return max(0, float(ttl)) if ttl > 0 else float(window)  # type: ignore
                except Exception:
                    return float(window)
            else:
                # Memory backend - estimate based on window
                return float(window)

        # If there are remaining requests, the window is not full
        return 0.0
