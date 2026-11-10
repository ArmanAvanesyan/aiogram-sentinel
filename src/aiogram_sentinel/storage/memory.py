"""In-memory storage backends for aiogram-sentinel."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Literal

from ..native import DebounceCore, RateCore, load_native, validate_engine
from .base import DebounceBackend, RateLimiterBackend, validate_interval


def _native_key(value: str) -> bytes:
    """Preserve every Python str code point, including unpaired surrogates."""
    return str.encode(value, "utf-8", "surrogatepass")


class MemoryRateLimiter(RateLimiterBackend):
    """In-memory rate limiter using sliding window with TTL cleanup."""

    def __init__(self, *, engine: Literal["python", "rust"] = "python") -> None:
        """Initialize one process-local engine; no implicit fallback is performed."""
        validate_engine(engine)
        self.engine = engine
        self._native: RateCore | None = (
            load_native().RateLimiterCore() if engine == "rust" else None
        )
        self._counters: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool:
        """Check if request is allowed and increment counter."""
        validate_interval(max_events, "max_events")
        validate_interval(per_seconds, "per_seconds")
        if self._native is not None:
            return self._native.allow(
                _native_key(key), max_events, per_seconds, time.monotonic()
            )
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries
            counter = self._cleanup_old_entries(key, now, per_seconds)
            # Keep the deque local instead of repeating dictionary lookups.
            if len(counter) < max_events:
                counter.append(now)
                return True
            return False

    async def get_remaining(self, key: str, max_events: int, per_seconds: int) -> int:
        """Get remaining requests in current window."""
        validate_interval(max_events, "max_events")
        validate_interval(per_seconds, "per_seconds")
        if self._native is not None:
            return self._native.remaining(
                _native_key(key), max_events, per_seconds, time.monotonic()
            )
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries
            counter = self._cleanup_old_entries(key, now, per_seconds)
            current_count = len(counter)
            return max(0, max_events - current_count)

    def _cleanup_old_entries(
        self, key: str, now: float, per_seconds: int
    ) -> deque[float]:
        """Remove entries older than the window."""
        window_start = now - per_seconds
        counter = self._counters[key]
        # Remove old entries from the left
        while counter and counter[0] < window_start:
            counter.popleft()
        return counter

    # Convenience methods for tests
    async def increment_rate_limit(self, key: str, window: int) -> int:
        """Increment rate limit counter and return current count."""
        if self._native is not None:
            return self._native.increment(_native_key(key), window, time.monotonic())
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries
            counter = self._cleanup_old_entries(key, now, window)
            counter.append(now)
            return len(counter)

    async def get_rate_limit(self, key: str) -> int:
        """Get current rate limit count for key."""
        if self._native is not None:
            return self._native.count(_native_key(key), time.monotonic())
        async with self._lock:
            now = time.monotonic()
            # Clean up old entries (use a reasonable default window)
            counter = self._cleanup_old_entries(key, now, 60)
            return len(counter)

    async def reset_rate_limit(self, key: str) -> None:
        """Reset rate limit for key."""
        if self._native is not None:
            self._native.reset(_native_key(key))
            return
        async with self._lock:
            if key in self._counters:
                self._counters[key].clear()


class MemoryDebounce(DebounceBackend):
    """In-memory debounce backend using monotonic time."""

    def __init__(self, *, engine: Literal["python", "rust"] = "python") -> None:
        """Initialize one process-local engine; no implicit fallback is performed."""
        validate_engine(engine)
        self.engine = engine
        self._native: DebounceCore | None = (
            load_native().DebounceCore() if engine == "rust" else None
        )
        self._store: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def seen(self, key: str, window_seconds: int, fingerprint: str) -> bool:
        """Check if fingerprint was seen within window and record it."""
        validate_interval(window_seconds, "window_seconds")
        if self._native is not None:
            return self._native.seen(
                _native_key(key),
                window_seconds,
                _native_key(fingerprint),
                time.monotonic(),
            )
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
        if self._native is not None:
            self._native.set(_native_key(key), delay, time.monotonic())
            return
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
        if self._native is not None:
            return self._native.active(_native_key(key), time.monotonic())
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
        if self._native is not None:
            return {
                bytes(key).decode("utf-8", "surrogatepass"): value
                for key, value in self._native.snapshot()
            }
        return self._store
