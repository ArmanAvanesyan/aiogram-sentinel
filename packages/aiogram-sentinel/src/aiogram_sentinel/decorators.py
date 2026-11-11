"""Decorators for aiogram-sentinel."""

from __future__ import annotations

import warnings
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

    Deprecated:
        Use @policy() with PolicyRegistry instead. Will be removed in v2.0.0.
    """

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        warnings.warn(
            "@rate_limit is deprecated, use @policy() with PolicyRegistry instead. "
            "Will be removed in v2.0.0",
            DeprecationWarning,
            stacklevel=2,
        )
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

    Deprecated:
        Use @policy() with PolicyRegistry instead. Will be removed in v2.0.0.
    """

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        warnings.warn(
            "@debounce is deprecated, use @policy() with PolicyRegistry instead. "
            "Will be removed in v2.0.0",
            DeprecationWarning,
            stacklevel=2,
        )
        # Store debounce configuration on the handler
        handler.sentinel_debounce = (window_seconds, scope)  # type: ignore
        return handler

    return decorator
