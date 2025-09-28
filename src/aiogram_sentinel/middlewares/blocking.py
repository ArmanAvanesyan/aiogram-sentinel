"""Blocking middleware for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..storage.base import BlocklistBackend


class BlockingMiddleware(BaseMiddleware):
    """Middleware for early blocking of users in blocklist."""

    def __init__(self, blocklist_backend: BlocklistBackend) -> None:
        """Initialize the blocking middleware.

        Args:
            blocklist_backend: Blocklist backend instance
        """
        super().__init__()
        self._blocklist_backend = blocklist_backend

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process the event through blocking middleware."""
        # Extract user ID from event
        user_id = self._extract_user_id(event)

        # Skip blocking check for anonymous users (user_id = 0)
        if user_id == 0:
            return await handler(event, data)

        # Check if user is blocked
        is_blocked = await self._blocklist_backend.is_blocked(user_id)

        if is_blocked:
            # User is blocked - short-circuit processing
            data["sentinel_blocked"] = True
            return  # Stop processing immediately

        # User is not blocked - continue to next middleware/handler
        return await handler(event, data)

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
