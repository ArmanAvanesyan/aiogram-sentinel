"""Redis storage backends for aiogram-sentinel."""

from __future__ import annotations

import time
from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..exceptions import BackendOperationError
from .base import DebounceBackend, RateLimiterBackend, validate_interval


def _k(prefix: str, *parts: str) -> str:
    """Build namespaced Redis key."""
    return f"{prefix}:{':'.join(parts)}"


class RedisRateLimiter(RateLimiterBackend):
    """Redis rate limiter using INCR + EXPIRE pattern."""

    def __init__(self, redis: Redis, prefix: str) -> None:
        """Initialize the rate limiter."""
        self._redis = redis
        self._prefix = prefix

    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool:
        """Check if request is allowed and increment counter."""
        validate_interval(max_events, "max_events")
        validate_interval(per_seconds, "per_seconds")
        try:
            redis_key = _k(self._prefix, "rate", key)
            # Increment and expiry must commit together, including after a worker dies.
            count = await cast(
                Awaitable[int],
                self._redis.eval(
                    "local n = redis.call('INCR', KEYS[1]); "
                    "if redis.call('TTL', KEYS[1]) == -1 then "
                    "redis.call('EXPIRE', KEYS[1], ARGV[1]); end; return n",
                    1,
                    redis_key,
                    str(per_seconds),
                ),
            )
            return int(count) <= max_events
        except RedisError as e:
            raise BackendOperationError(f"Failed to check rate limit: {e}") from e

    async def get_remaining(self, key: str, max_events: int, per_seconds: int) -> int:
        """Get remaining requests in current window."""
        validate_interval(max_events, "max_events")
        validate_interval(per_seconds, "per_seconds")
        try:
            redis_key = _k(self._prefix, "rate", key)
            val = await self._redis.get(redis_key)
            return max(0, max_events - int(val or 0))
        except RedisError as e:
            raise BackendOperationError(f"Failed to get remaining: {e}") from e


class RedisDebounce(DebounceBackend):
    """Redis debounce backend using SET NX EX pattern."""

    def __init__(self, redis: Redis, prefix: str) -> None:
        """Initialize the debounce backend."""
        self._redis = redis
        self._prefix = prefix

    async def seen(self, key: str, window_seconds: int, fingerprint: str) -> bool:
        """Check if fingerprint was seen within window and record it."""
        validate_interval(window_seconds, "window_seconds")
        try:
            fp = fingerprint  # Use fingerprint directly
            k = _k(self._prefix, "debounce", key, fp)
            added = await self._redis.set(
                k, int(time.time()), ex=window_seconds, nx=True
            )
            # nx=True => returns True if set, None if exists
            return added is None
        except RedisError as e:
            raise BackendOperationError(f"Failed to check debounce: {e}") from e
