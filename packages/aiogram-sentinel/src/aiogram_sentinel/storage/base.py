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


def validate_interval(value: object, name: str) -> None:
    """Validate public integer limits before storage calls (Redis-safe range)."""
    from ..exceptions import ConfigurationError

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= 2_147_483_647
    ):
        raise ConfigurationError(f"{name} must be an integer between 1 and 2147483647")
