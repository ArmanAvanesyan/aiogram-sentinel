"""Base protocols for storage backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RateLimiterBackend(Protocol):
    """Protocol for rate limiting storage backend."""

    async def get_rate_limit(self, key: str) -> int:
        """Get current rate limit count for key."""
        ...

    async def increment_rate_limit(self, key: str, window: int) -> int:
        """Increment rate limit count and return new count."""
        ...

    async def reset_rate_limit(self, key: str) -> None:
        """Reset rate limit count for key."""
        ...


@runtime_checkable
class DebounceBackend(Protocol):
    """Protocol for debouncing storage backend."""

    async def get_debounce(self, key: str) -> float | None:
        """Get last debounce timestamp for key."""
        ...

    async def set_debounce(self, key: str, timestamp: float) -> None:
        """Set debounce timestamp for key."""
        ...

    async def clear_debounce(self, key: str) -> None:
        """Clear debounce timestamp for key."""
        ...


@runtime_checkable
class BlocklistBackend(Protocol):
    """Protocol for blocklist storage backend."""

    async def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked."""
        ...

    async def block_user(self, user_id: int) -> None:
        """Block a user."""
        ...

    async def unblock_user(self, user_id: int) -> None:
        """Unblock a user."""
        ...

    async def get_blocked_users(self) -> set[int]:
        """Get all blocked user IDs."""
        ...


@runtime_checkable
class UserRepo(Protocol):
    """Protocol for user repository."""

    async def is_registered(self, user_id: int) -> bool:
        """Check if user is registered."""
        ...

    async def register_user(self, user_id: int, **kwargs: Any) -> None:
        """Register a new user."""
        ...

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        """Get user data."""
        ...

    async def update_user(self, user_id: int, **kwargs: Any) -> None:
        """Update user data."""
        ...
