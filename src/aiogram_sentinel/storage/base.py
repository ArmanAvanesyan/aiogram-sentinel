"""Base protocols for storage backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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
