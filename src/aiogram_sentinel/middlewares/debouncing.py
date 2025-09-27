"""Debouncing middleware for aiogram-sentinel."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..storage.base import DebounceBackend
from ..utils.keys import debounce_key, fingerprint


class DebounceMiddleware(BaseMiddleware):
    """Middleware for debouncing duplicate messages with fingerprinting."""

    def __init__(
        self,
        debounce_backend: DebounceBackend,
        default_delay: float = 1.0,
    ) -> None:
        """Initialize the debouncing middleware.
        
        Args:
            debounce_backend: Debounce backend instance
            default_delay: Default debounce delay in seconds
        """
        super().__init__()
        self._debounce_backend = debounce_backend
        self._default_delay = default_delay

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Process the event through debouncing middleware."""
        # Get debounce configuration
        delay = self._get_debounce_delay(handler, data)
        
        # Generate fingerprint for the event
        fp = self._generate_fingerprint(event)
        
        # Generate debounce key
        key = self._generate_debounce_key(event, handler, data, fp)
        
        # Check if already seen within delay window
        now = time.monotonic()
        last_seen = await self._debounce_backend.get_debounce(key)
        
        if last_seen and (now - last_seen) < delay:
            # Duplicate detected within window
            data["sentinel_debounced"] = True
            return  # Stop processing
        
        # Set debounce timestamp
        await self._debounce_backend.set_debounce(key, now)
        
        # Continue to next middleware/handler
        return await handler(event, data)

    def _get_debounce_delay(self, handler: Callable[..., Any], data: Dict[str, Any]) -> float:
        """Get debounce delay from handler or use default."""
        # Check if handler has debounce configuration
        if hasattr(handler, "_sentinel_debounce"):  # type: ignore
            config = getattr(handler, "_sentinel_debounce")  # type: ignore
            return config.get("delay", self._default_delay)
        
        # Check data for debounce configuration
        if "sentinel_debounce" in data:
            config = data["sentinel_debounce"]
            return config.get("delay", self._default_delay)
        
        # Use default
        return self._default_delay

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
            return getattr(event, "text")  # type: ignore
        
        # Try to get caption from message
        if hasattr(event, "caption") and getattr(event, "caption", None):  # type: ignore
            return getattr(event, "caption")  # type: ignore
        
        # Try to get data from callback query
        if hasattr(event, "data") and getattr(event, "data", None):  # type: ignore
            return getattr(event, "data")  # type: ignore
        
        # Try to get query from inline query
        if hasattr(event, "query") and getattr(event, "query", None):  # type: ignore
            return getattr(event, "query")  # type: ignore
        
        # Return empty string if no content found
        return ""

    def _generate_debounce_key(
        self, 
        event: TelegramObject, 
        handler: Callable[..., Any], 
        data: Dict[str, Any], 
        fp: str
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
        
        # Include fingerprint in key
        scope_kwargs["fp"] = fp
        
        return debounce_key(user_id, handler_name, **scope_kwargs)

    def _extract_user_id(self, event: TelegramObject) -> int:
        """Extract user ID from event."""
        # Try different event types
        if hasattr(event, "from_user") and getattr(event, "from_user", None):  # type: ignore
            return getattr(getattr(event, "from_user"), "id", 0)  # type: ignore
        elif hasattr(event, "user") and getattr(event, "user", None):  # type: ignore
            return getattr(getattr(event, "user"), "id", 0)  # type: ignore
        elif hasattr(event, "chat") and getattr(event, "chat", None):  # type: ignore
            return getattr(getattr(event, "chat"), "id", 0)  # type: ignore
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
        setattr(handler, "_sentinel_debounce", {"delay": delay})  # type: ignore
        return handler
    return decorator
