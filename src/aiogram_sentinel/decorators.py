"""Decorators for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def rate_limit(
    max_events: int, per_seconds: int, *, scope: str | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to set rate limit configuration on handlers.

    Args:
        max_events: Maximum number of events per time window
        per_seconds: Time window in seconds
        scope: Optional scope for rate limiting
    """

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        # Store rate limit configuration on the handler
        handler.sentinel_rate_limit = (max_events, per_seconds, scope)  # type: ignore
        return handler

    return decorator


def debounce(
    window_seconds: int, *, scope: str | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to set debounce configuration on handlers.

    Args:
        window_seconds: Debounce window in seconds
        scope: Optional scope for debouncing
    """

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        # Store debounce configuration on the handler
        handler.sentinel_debounce = (window_seconds, scope)  # type: ignore
        return handler

    return decorator


def require_registered(
    required: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to mark a handler as requiring user registration.

    Args:
        required: Whether registration is required
    """

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        # Store registration requirement on the handler
        handler.sentinel_require_registered = required  # type: ignore
        return handler

    return decorator
