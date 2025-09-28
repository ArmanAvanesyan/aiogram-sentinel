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

    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool:
        """Check if request is allowed and increment counter."""
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries
            self._cleanup_old_entries(key, now, per_seconds)
            # Check if under limit
            if len(self._counters[key]) < max_events:
                # Add current timestamp
                self._counters[key].append(now)
                return True
            return False

    async def get_remaining(self, key: str, max_events: int, per_seconds: int) -> int:
        """Get remaining requests in current window."""
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries
            self._cleanup_old_entries(key, now, per_seconds)
            current_count = len(self._counters[key])
            return max(0, max_events - current_count)

    def _cleanup_old_entries(self, key: str, now: float, per_seconds: int) -> None:
        """Remove entries older than the window."""
        window_start = now - per_seconds
        counter = self._counters[key]
        # Remove old entries from the left
        while counter and counter[0] < window_start:
            counter.popleft()


class MemoryDebounce(DebounceBackend):
    """In-memory debounce backend using monotonic time."""

    def __init__(self) -> None:
        """Initialize the debounce backend."""
        self._store: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def seen(self, key: str, window_seconds: int, fingerprint: str) -> bool:
        """Check if fingerprint was seen within window and record it."""
        k = f"{key}:{fingerprint}"
        async with self._lock:
            now = time.monotonic()
            ts = self._store.get(k, 0)
            if ts and ts + window_seconds > now:
                return True
            self._store[k] = now
            return False


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

    async def set_blocked(self, user_id: int, blocked: bool) -> None:
        """Set user blocked status."""
        async with self._lock:
            if blocked:
                self._blocked_users.add(user_id)
            else:
                self._blocked_users.discard(user_id)


class MemoryUserRepo(UserRepo):
    """In-memory user repository implementation."""

    def __init__(self) -> None:
        """Initialize the user repository."""
        self._users: dict[int, dict] = {}
        self._lock = asyncio.Lock()

    async def ensure_user(self, user_id: int, *, username: str | None = None) -> None:
        """Ensure user exists, creating if necessary."""
        async with self._lock:
            if user_id not in self._users:
                self._users[user_id] = {
                    "user_id": user_id,
                    "registered_at": time.monotonic(),
                }
            if username:
                self._users[user_id]["username"] = username

    async def is_registered(self, user_id: int) -> bool:
        """Check if user is registered."""
        async with self._lock:
            return user_id in self._users

    async def register_user(self, user_id: int, **kwargs: Any) -> None:
        """Register a user with optional data."""
        async with self._lock:
            if user_id not in self._users:
                self._users[user_id] = {
                    "user_id": user_id,
                    "registered_at": time.monotonic(),
                }
            # Update with provided data
            for key, value in kwargs.items():
                self._users[user_id][key] = value

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        """Get user data by ID."""
        async with self._lock:
            return self._users.get(user_id)
