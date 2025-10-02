"""Redis storage backends for aiogram-sentinel."""

from __future__ import annotations

import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..exceptions import BackendOperationError
from .base import DebounceBackend, RateLimiterBackend


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
        try:
            redis_key = _k(self._prefix, "rate", key)
            # Use pipeline for atomic operation
            pipe = self._redis.pipeline()
            pipe.incr(redis_key)
            pipe.ttl(redis_key)
            count, ttl = await pipe.execute()
            if ttl == -1:  # Set TTL if absent
                await self._redis.expire(redis_key, per_seconds)
            return int(count) <= max_events
        except RedisError as e:
            raise BackendOperationError(f"Failed to check rate limit: {e}") from e

    async def get_remaining(self, key: str, max_events: int, per_seconds: int) -> int:
        """Get remaining requests in current window."""
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
