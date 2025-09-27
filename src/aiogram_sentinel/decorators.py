"""Decorators for aiogram-sentinel."""

from __future__ import annotations

from typing import Any, Callable


def rate_limit(limit: int = 10, window: int = 60) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to set rate limit configuration on handlers.
    
    Args:
        limit: Maximum number of requests per window
        window: Time window in seconds
    """
    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        # Store rate limit configuration on the handler
        setattr(handler, "_sentinel_rate_limit", {"limit": limit, "window": window})  # type: ignore
        return handler
    return decorator


def debounce(delay: float = 1.0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to set debounce configuration on handlers.
    
    Args:
        delay: Debounce delay in seconds
    """
    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        # Store debounce configuration on the handler
        setattr(handler, "_sentinel_debounce", {"delay": delay})  # type: ignore
        return handler
    return decorator


def require_registered() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to mark a handler as requiring user registration."""
    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        # Store registration requirement on the handler
        setattr(handler, "_sentinel_require_registered", True)  # type: ignore
        return handler
    return decorator
