"""Authentication middleware for aiogram-sentinel."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..storage.base import UserRepo


class AuthMiddleware(BaseMiddleware):
    """Middleware for user authentication and context management."""

    def __init__(
        self,
        user_repo: UserRepo,
        resolve_user: Optional[Callable[[TelegramObject, Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]]] = None,
    ) -> None:
        """Initialize the authentication middleware.
        
        Args:
            user_repo: User repository backend instance
            resolve_user: Optional hook for custom user resolution logic
        """
        super().__init__()
        self._user_repo = user_repo
        self._resolve_user = resolve_user

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Process the event through authentication middleware."""
        # Extract user information from event
        user_id, username = self._extract_user_info(event)
        
        # Skip auth for anonymous users (user_id = 0)
        if user_id == 0:
            return await handler(event, data)
        
        # Ensure minimal user record exists
        await self._ensure_user(user_id, username)
        
        # Call optional resolve_user hook
        if self._resolve_user:
            user_context = await self._resolve_user(event, data)
            
            # Check if resolver vetoed the request
            if user_context is None:
                # Resolver vetoed - stop processing
                data["sentinel_auth_vetoed"] = True
                return
            
            # Populate user context
            data["user_context"] = user_context
            data["user_exists"] = True
        else:
            # No resolver - just mark user as existing
            data["user_exists"] = True
        
        # Continue to next middleware/handler
        return await handler(event, data)

    async def _ensure_user(self, user_id: int, username: Optional[str] = None) -> None:
        """Ensure minimal user record exists in repository."""
        # Check if user is already registered
        is_registered = await self._user_repo.is_registered(user_id)
        
        if not is_registered:
            # Register new user with minimal data
            user_data: Dict[str, Any] = {
                "registered_at": time.monotonic(),
            }
            
            if username:
                user_data["username"] = username
            
            await self._user_repo.register_user(user_id, **user_data)

    def _extract_user_info(self, event: TelegramObject) -> tuple[int, Optional[str]]:
        """Extract user ID and username from event."""
        # Try different event types
        if hasattr(event, "from_user") and getattr(event, "from_user", None):  # type: ignore
            user = getattr(event, "from_user")  # type: ignore
            user_id = getattr(user, "id", 0)  # type: ignore
            username = getattr(user, "username", None)  # type: ignore
            return user_id, username
        elif hasattr(event, "user") and getattr(event, "user", None):  # type: ignore
            user = getattr(event, "user")  # type: ignore
            user_id = getattr(user, "id", 0)  # type: ignore
            username = getattr(user, "username", None)  # type: ignore
            return user_id, username
        elif hasattr(event, "chat") and getattr(event, "chat", None):  # type: ignore
            chat = getattr(event, "chat")  # type: ignore
            user_id = getattr(chat, "id", 0)  # type: ignore
            username = getattr(chat, "username", None)  # type: ignore
            return user_id, username
        else:
            # Fallback for anonymous events
            return 0, None


def create_bot_veto_resolver() -> Callable[[TelegramObject, Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]]:
    """Create a resolver that vetoes bot users."""
    async def resolve_user(event: TelegramObject, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Resolve user and veto if bot."""
        # Extract user information
        if hasattr(event, "from_user") and getattr(event, "from_user", None):  # type: ignore
            user = getattr(event, "from_user")  # type: ignore
            is_bot = getattr(user, "is_bot", False)  # type: ignore
            
            if is_bot:
                # Veto bot users
                return None
            
            # Return user context for non-bot users
            return {
                "user_id": getattr(user, "id", 0),  # type: ignore
                "username": getattr(user, "username", None),  # type: ignore
                "first_name": getattr(user, "first_name", None),  # type: ignore
                "last_name": getattr(user, "last_name", None),  # type: ignore
                "is_bot": is_bot,
            }
        
        # No user info - veto
        return None
    
    return resolve_user


def create_blocked_veto_resolver(blocklist_backend: Any) -> Callable[[TelegramObject, Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]]:
    """Create a resolver that vetoes blocked users."""
    async def resolve_user(event: TelegramObject, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Resolve user and veto if blocked."""
        # Extract user ID
        if hasattr(event, "from_user") and getattr(event, "from_user", None):  # type: ignore
            user = getattr(event, "from_user")  # type: ignore
            user_id = getattr(user, "id", 0)  # type: ignore
            
            # Check if user is blocked
            is_blocked = await blocklist_backend.is_blocked(user_id)
            
            if is_blocked:
                # Veto blocked users
                return None
            
            # Return user context for non-blocked users
            return {
                "user_id": user_id,
                "username": getattr(user, "username", None),  # type: ignore
                "first_name": getattr(user, "first_name", None),  # type: ignore
                "last_name": getattr(user, "last_name", None),  # type: ignore
                "is_bot": getattr(user, "is_bot", False),  # type: ignore
                "is_blocked": is_blocked,
            }
        
        # No user info - veto
        return None
    
    return resolve_user
