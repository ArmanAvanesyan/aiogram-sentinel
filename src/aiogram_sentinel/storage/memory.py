"""In-memory storage backends for aiogram-sentinel."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from .base import DebounceBackend, RateLimiterBackend


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

    # Convenience methods for tests
    async def increment_rate_limit(self, key: str, window: int) -> int:
        """Increment rate limit counter and return current count."""
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries
            self._cleanup_old_entries(key, now, window)
            # Add current timestamp
            self._counters[key].append(now)
            return len(self._counters[key])

    async def get_rate_limit(self, key: str) -> int:
        """Get current rate limit count for key."""
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries (use a reasonable default window)
            self._cleanup_old_entries(key, now, 60)  # 60 second default window
            return len(self._counters[key])

    async def reset_rate_limit(self, key: str) -> None:
        """Reset rate limit for key."""
        async with self._lock:
            if key in self._counters:
                self._counters[key].clear()


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

    # Convenience methods for tests
    async def set_debounce(self, key: str, delay: float) -> None:
        """Set debounce for a key."""
        async with self._lock:
            now = time.monotonic()
            if delay <= 0:
                # For zero or negative delay, don't set debounce
                if key in self._store:
                    del self._store[key]
            else:
                self._store[key] = now + delay

    async def is_debounced(self, key: str) -> bool:
        """Check if key is currently debounced."""
        async with self._lock:
            now = time.monotonic()
            ts = self._store.get(key, 0)
            if ts and ts >= now:  # Use >= for boundary case
                return True
            # Clean up expired entries
            if key in self._store:
                del self._store[key]
            return False

    @property
    def _debounces(self) -> dict[str, float]:
        """Access to internal storage for testing."""
        return self._store
