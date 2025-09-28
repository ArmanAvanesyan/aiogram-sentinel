"""Factory for creating storage backends."""

from __future__ import annotations

from ..config import SentinelConfig
from ..exceptions import ConfigurationError
from ..types import BackendsBundle


def build_backends(config: SentinelConfig) -> BackendsBundle:
    """Build storage backends based on configuration."""
    if config.backend == "memory":
        return _build_memory_backends()
    elif config.backend == "redis":
        return _build_redis_backends(config)
    else:
        raise ConfigurationError(f"Unsupported backend: {config.backend}")


def _build_memory_backends() -> BackendsBundle:
    """Build in-memory backends."""
    from .memory import (
        MemoryBlocklist,
        MemoryDebounce,
        MemoryRateLimiter,
        MemoryUserRepo,
    )

    return BackendsBundle(
        rate_limiter=MemoryRateLimiter(),
        debounce=MemoryDebounce(),
        blocklist=MemoryBlocklist(),
        user_repo=MemoryUserRepo(),
    )


def _build_redis_backends(config: SentinelConfig) -> BackendsBundle:
    """Build Redis backends."""
    try:
        from redis.asyncio import Redis
    except ImportError as e:
        raise ConfigurationError(
            "Redis backend requires redis package. Install with: pip install redis"
        ) from e

    from .redis import (
        RedisBlocklist,
        RedisDebounce,
        RedisRateLimiter,
        RedisUserRepo,
    )

    try:
        # Create Redis connection
        redis: Redis = Redis.from_url(config.redis_url)  # type: ignore

        return BackendsBundle(
            rate_limiter=RedisRateLimiter(redis, config.redis_prefix),
            debounce=RedisDebounce(redis, config.redis_prefix),
            blocklist=RedisBlocklist(redis, config.redis_prefix),
            user_repo=RedisUserRepo(redis, config.redis_prefix),
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to create Redis connection: {e}") from e
