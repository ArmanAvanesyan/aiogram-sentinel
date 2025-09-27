"""Decorators for aiogram-sentinel."""

from __future__ import annotations

import functools
import time
from typing import Any, Awaitable, Callable, TypeVar

from aiogram.types import TelegramObject

from .exceptions import MiddlewareError
from .utils.keys import debounce_key, rate_key

T = TypeVar("T", bound=TelegramObject)


def rate_limit(
    limit: int = 10,
    window: int = 60,
    key_func: Callable[[T], str] | None = None,
) -> Callable[[Callable[[T, dict[str, Any]], Awaitable[Any]]], Callable[[T, dict[str, Any]], Awaitable[Any]]]:
    """Decorator to rate limit handler calls.
    
    Args:
        limit: Maximum number of calls per window
        window: Time window in seconds
        key_func: Function to generate rate limit key from event
    """
    def decorator(
        handler: Callable[[T, dict[str, Any]], Awaitable[Any]]
    ) -> Callable[[T, dict[str, Any]], Awaitable[Any]]:
        @functools.wraps(handler)
        async def wrapper(event: T, data: dict[str, Any]) -> Any:
            # Get rate limiter from middleware data
            rate_limiter = data.get("rate_limiter")
            if not rate_limiter:
                raise MiddlewareError("Rate limiter not available in middleware data")
            
            # Generate key
            if key_func:
                key = key_func(event)
            else:
                # Default key generation
                user_id = getattr(event, "from_user", {}).get("id", 0) if hasattr(event, "from_user") else 0
                handler_name = handler.__name__
                key = rate_key(user_id, handler_name)
            
            # Check current count
            current_count = await rate_limiter.get_rate_limit(key)
            if current_count >= limit:
                # Rate limit exceeded
                return  # Skip handler execution
            
            # Increment counter
            await rate_limiter.increment_rate_limit(key, window)
            
            # Execute handler
            return await handler(event, data)
        
        return wrapper
    return decorator


def debounce(
    delay: float = 1.0,
    key_func: Callable[[T], str] | None = None,
) -> Callable[[Callable[[T, dict[str, Any]], Awaitable[Any]]], Callable[[T, dict[str, Any]], Awaitable[Any]]]:
    """Decorator to debounce handler calls.
    
    Args:
        delay: Minimum delay between calls in seconds
        key_func: Function to generate debounce key from event
    """
    def decorator(
        handler: Callable[[T, dict[str, Any]], Awaitable[Any]]
    ) -> Callable[[T, dict[str, Any]], Awaitable[Any]]:
        @functools.wraps(handler)
        async def wrapper(event: T, data: dict[str, Any]) -> Any:
            # Get debounce backend from middleware data
            debounce_backend = data.get("debounce_backend")
            if not debounce_backend:
                raise MiddlewareError("Debounce backend not available in middleware data")
            
            # Generate key
            if key_func:
                key = key_func(event)
            else:
                # Default key generation
                user_id = getattr(event, "from_user", {}).get("id", 0) if hasattr(event, "from_user") else 0
                handler_name = handler.__name__
                key = debounce_key(user_id, handler_name)
            
            # Check if debounced
            now = time.monotonic()
            last_call = await debounce_backend.get_debounce(key)
            
            if last_call and (now - last_call) < delay:
                # Still within debounce window
                return  # Skip handler execution
            
            # Set debounce timestamp
            await debounce_backend.set_debounce(key, now)
            
            # Execute handler
            return await handler(event, data)
        
        return wrapper
    return decorator


def require_registered(
    key_func: Callable[[T], int] | None = None,
) -> Callable[[Callable[[T, dict[str, Any]], Awaitable[Any]]], Callable[[T, dict[str, Any]], Awaitable[Any]]]:
    """Decorator to require user registration.
    
    Args:
        key_func: Function to extract user ID from event
    """
    def decorator(
        handler: Callable[[T, dict[str, Any]], Awaitable[Any]]
    ) -> Callable[[T, dict[str, Any]], Awaitable[Any]]:
        @functools.wraps(handler)
        async def wrapper(event: T, data: dict[str, Any]) -> Any:
            # Get user repository from middleware data
            user_repo = data.get("user_repo")
            if not user_repo:
                raise MiddlewareError("User repository not available in middleware data")
            
            # Extract user ID
            if key_func:
                user_id = key_func(event)
            else:
                # Default user ID extraction
                user_id = getattr(event, "from_user", {}).get("id", 0) if hasattr(event, "from_user") else 0
            
            if not user_id:
                # No user ID available
                return  # Skip handler execution
            
            # Check if user is registered
            is_registered = await user_repo.is_registered(user_id)
            if not is_registered:
                # User not registered
                return  # Skip handler execution
            
            # Execute handler
            return await handler(event, data)
        
        return wrapper
    return decorator
