"""Redis storage backends for aiogram-sentinel."""

from __future__ import annotations

import time
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..exceptions import BackendOperationError
from .base import BlocklistBackend, DebounceBackend, RateLimiterBackend, UserRepo


def _k(prefix: str, *parts: str) -> str:
    """Build namespaced Redis key."""
    return f"{prefix}:{':'.join(parts)}"


class RedisRateLimiter(RateLimiterBackend):
    """Redis rate limiter using INCR + EXPIRE pattern."""

    def __init__(self, redis: Redis, prefix: str) -> None:
        """Initialize the rate limiter."""
        self._redis = redis
        self._prefix = prefix

    async def get_rate_limit(self, key: str) -> int:
        """Get current rate limit count for key."""
        try:
            redis_key = _k(self._prefix, "rate", key)
            count = await self._redis.get(redis_key)
            return int(count) if count else 0
        except RedisError as e:
            raise BackendOperationError(f"Failed to get rate limit: {e}") from e

    async def increment_rate_limit(self, key: str, window: int) -> int:
        """Increment rate limit count and return new count."""
        try:
            redis_key = _k(self._prefix, "rate", key)
            # Use pipeline for atomic operation
            pipe = self._redis.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window)
            results = await pipe.execute()
            return results[0]  # Return the incremented count
        except RedisError as e:
            raise BackendOperationError(f"Failed to increment rate limit: {e}") from e

    async def reset_rate_limit(self, key: str) -> None:
        """Reset rate limit count for key."""
        try:
            redis_key = _k(self._prefix, "rate", key)
            await self._redis.delete(redis_key)
        except RedisError as e:
            raise BackendOperationError(f"Failed to reset rate limit: {e}") from e


class RedisDebounce(DebounceBackend):
    """Redis debounce backend using SET NX EX pattern."""

    def __init__(self, redis: Redis, prefix: str) -> None:
        """Initialize the debounce backend."""
        self._redis = redis
        self._prefix = prefix

    async def get_debounce(self, key: str) -> float | None:
        """Get last debounce timestamp for key."""
        try:
            redis_key = _k(self._prefix, "debounce", key)
            timestamp = await self._redis.get(redis_key)
            return float(timestamp) if timestamp else None
        except RedisError as e:
            raise BackendOperationError(f"Failed to get debounce: {e}") from e

    async def set_debounce(self, key: str, timestamp: float) -> None:
        """Set debounce timestamp for key."""
        try:
            redis_key = _k(self._prefix, "debounce", key)
            # Use SET with NX (only if not exists) and EX (expire)
            await self._redis.set(redis_key, str(timestamp), nx=True, ex=300)  # 5 min TTL
        except RedisError as e:
            raise BackendOperationError(f"Failed to set debounce: {e}") from e

    async def clear_debounce(self, key: str) -> None:
        """Clear debounce timestamp for key."""
        try:
            redis_key = _k(self._prefix, "debounce", key)
            await self._redis.delete(redis_key)
        except RedisError as e:
            raise BackendOperationError(f"Failed to clear debounce: {e}") from e


class RedisBlocklist(BlocklistBackend):
    """Redis blocklist backend using SADD/SREM/SISMEMBER."""

    def __init__(self, redis: Redis, prefix: str) -> None:
        """Initialize the blocklist backend."""
        self._redis = redis
        self._prefix = prefix
        self._blocklist_key = _k(self._prefix, "blocklist")

    async def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked."""
        try:
            result = await self._redis.sismember(self._blocklist_key, str(user_id))  # type: ignore
            return bool(result)  # type: ignore
        except RedisError as e:
            raise BackendOperationError(f"Failed to check blocklist: {e}") from e

    async def block_user(self, user_id: int) -> None:
        """Block a user."""
        try:
            await self._redis.sadd(self._blocklist_key, str(user_id))  # type: ignore
        except RedisError as e:
            raise BackendOperationError(f"Failed to block user: {e}") from e

    async def unblock_user(self, user_id: int) -> None:
        """Unblock a user."""
        try:
            await self._redis.srem(self._blocklist_key, str(user_id))  # type: ignore
        except RedisError as e:
            raise BackendOperationError(f"Failed to unblock user: {e}") from e

    async def get_blocked_users(self) -> set[int]:
        """Get all blocked user IDs."""
        try:
            members = await self._redis.smembers(self._blocklist_key)  # type: ignore
            result: set[int] = set()
            for member in members:  # type: ignore
                if isinstance(member, (str, bytes)):
                    member_str = member.decode() if isinstance(member, bytes) else member
                    if member_str.isdigit():
                        result.add(int(member_str))
            return result
        except RedisError as e:
            raise BackendOperationError(f"Failed to get blocked users: {e}") from e


class RedisUserRepo(UserRepo):
    """Redis user repository using HSETNX/HSET."""

    def __init__(self, redis: Redis, prefix: str) -> None:
        """Initialize the user repository."""
        self._redis = redis
        self._prefix = prefix

    async def is_registered(self, user_id: int) -> bool:
        """Check if user is registered."""
        try:
            redis_key = _k(self._prefix, "user", str(user_id))
            result = await self._redis.hexists(redis_key, "registered")  # type: ignore
            return bool(result)  # type: ignore
        except RedisError as e:
            raise BackendOperationError(f"Failed to check registration: {e}") from e

    async def register_user(self, user_id: int, **kwargs: Any) -> None:
        """Register a new user."""
        try:
            redis_key = _k(self._prefix, "user", str(user_id))
            # Use HSETNX to set registered=1 only if not exists
            await self._redis.hsetnx(redis_key, "registered", "1")  # type: ignore
            await self._redis.hset(redis_key, "user_id", str(user_id))  # type: ignore
            await self._redis.hset(redis_key, "registered_at", str(time.monotonic()))  # type: ignore
            
            # Set additional fields
            for key, value in kwargs.items():
                await self._redis.hset(redis_key, key, str(value))  # type: ignore
        except RedisError as e:
            raise BackendOperationError(f"Failed to register user: {e}") from e

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        """Get user data."""
        try:
            redis_key = _k(self._prefix, "user", str(user_id))
            data = await self._redis.hgetall(redis_key)  # type: ignore
            if not data:
                return None
            
            # Convert bytes to strings and parse values
            result: dict[str, Any] = {}
            for key, value in data.items():  # type: ignore
                key_str = key.decode() if isinstance(key, bytes) else str(key)  # type: ignore
                value_str = value.decode() if isinstance(value, bytes) else str(value)  # type: ignore
                
                # Try to parse numeric values
                if value_str.isdigit():
                    result[key_str] = int(value_str)
                elif value_str.replace(".", "").isdigit():
                    result[key_str] = float(value_str)
                else:
                    result[key_str] = value_str
            
            return result
        except RedisError as e:
            raise BackendOperationError(f"Failed to get user: {e}") from e

    async def update_user(self, user_id: int, **kwargs: Any) -> None:
        """Update user data."""
        try:
            redis_key = _k(self._prefix, "user", str(user_id))
            # Update fields
            for key, value in kwargs.items():
                await self._redis.hset(redis_key, key, str(value))  # type: ignore
        except RedisError as e:
            raise BackendOperationError(f"Failed to update user: {e}") from e
