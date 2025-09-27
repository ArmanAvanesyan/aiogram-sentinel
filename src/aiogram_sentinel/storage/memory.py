"""In-memory storage backends for aiogram-sentinel."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Any

from .base import BlocklistBackend, DebounceBackend, RateLimiterBackend, UserRepo


class MemoryRateLimiter(RateLimiterBackend):
    """In-memory rate limiter using sliding window with TTL cleanup."""

    def __init__(self) -> None:
        """Initialize the rate limiter."""
        self._counters: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def get_rate_limit(self, key: str) -> int:
        """Get current rate limit count for key."""
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries
            self._cleanup_old_entries(key, now)
            return len(self._counters[key])

    async def increment_rate_limit(self, key: str, window: int) -> int:
        """Increment rate limit count and return new count."""
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries
            self._cleanup_old_entries(key, now)
            # Add current timestamp
            self._counters[key].append(now)
            return len(self._counters[key])

    async def reset_rate_limit(self, key: str) -> None:
        """Reset rate limit count for key."""
        async with self._lock:
            self._counters[key].clear()

    def _cleanup_old_entries(self, key: str, now: float) -> None:
        """Remove entries older than the window."""
        window_start = now - 60  # 60 second window
        counter = self._counters[key]
        # Remove old entries from the left
        while counter and counter[0] < window_start:
            counter.popleft()


class MemoryDebounce(DebounceBackend):
    """In-memory debounce backend using monotonic time."""

    def __init__(self) -> None:
        """Initialize the debounce backend."""
        self._timestamps: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get_debounce(self, key: str) -> float | None:
        """Get last debounce timestamp for key."""
        async with self._lock:
            return self._timestamps.get(key)

    async def set_debounce(self, key: str, timestamp: float) -> None:
        """Set debounce timestamp for key."""
        async with self._lock:
            self._timestamps[key] = timestamp

    async def clear_debounce(self, key: str) -> None:
        """Clear debounce timestamp for key."""
        async with self._lock:
            self._timestamps.pop(key, None)


class MemoryBlocklist(BlocklistBackend):
    """In-memory blocklist backend using set semantics."""

    def __init__(self) -> None:
        """Initialize the blocklist backend."""
        self._blocked_users: set[int] = set()
        self._lock = asyncio.Lock()

    async def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked."""
        async with self._lock:
            return user_id in self._blocked_users

    async def block_user(self, user_id: int) -> None:
        """Block a user."""
        async with self._lock:
            self._blocked_users.add(user_id)

    async def unblock_user(self, user_id: int) -> None:
        """Unblock a user."""
        async with self._lock:
            self._blocked_users.discard(user_id)

    async def get_blocked_users(self) -> set[int]:
        """Get all blocked user IDs."""
        async with self._lock:
            return self._blocked_users.copy()


class MemoryUserRepo(UserRepo):
    """In-memory user repository implementation."""

    def __init__(self) -> None:
        """Initialize the user repository."""
        self._users: dict[int, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def is_registered(self, user_id: int) -> bool:
        """Check if user is registered."""
        async with self._lock:
            return user_id in self._users

    async def register_user(self, user_id: int, **kwargs: Any) -> None:
        """Register a new user."""
        async with self._lock:
            self._users[user_id] = {
                "user_id": user_id,
                "registered_at": time.monotonic(),
                **kwargs,
            }

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        """Get user data."""
        async with self._lock:
            return self._users.get(user_id)

    async def update_user(self, user_id: int, **kwargs: Any) -> None:
        """Update user data."""
        async with self._lock:
            if user_id in self._users:
                self._users[user_id].update(kwargs)
