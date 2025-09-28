"""Base protocols for storage backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RateLimiterBackend(Protocol):
    """Protocol for rate limiting storage backend."""

    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool:
        """Check if request is allowed and increment counter."""
        ...

    async def get_remaining(self, key: str, max_events: int, per_seconds: int) -> int:
        """Get remaining requests in current window."""
        ...


@runtime_checkable
class DebounceBackend(Protocol):
    """Protocol for debouncing storage backend."""

    async def seen(self, key: str, window_seconds: int, fingerprint: str) -> bool:
        """Check if fingerprint was seen within window and record it."""
        ...


@runtime_checkable
class BlocklistBackend(Protocol):
    """Protocol for blocklist storage backend."""

    async def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked."""
        ...

    async def set_blocked(self, user_id: int, blocked: bool) -> None:
        """Set user blocked status."""
        ...


@runtime_checkable
class UserRepo(Protocol):
    """Protocol for user repository."""

    async def ensure_user(self, user_id: int, *, username: str | None = None) -> None:
        """Ensure user exists, creating if necessary."""
        ...

    async def is_registered(self, user_id: int) -> bool:
        """Check if user is registered."""
        ...

    async def register_user(self, user_id: int, **kwargs: Any) -> None:
        """Register a user with optional data."""
        ...

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        """Get user data by ID."""
        ...
