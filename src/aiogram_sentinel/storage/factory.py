"""Factory for creating storage backends."""

from __future__ import annotations

from ..config import SentinelConfig
from ..exceptions import ConfigurationError
from ..types import InfraBundle


def build_infra(config: SentinelConfig) -> InfraBundle:
    """Build infrastructure backends (rate_limiter + debounce) based on configuration."""
    if config.backend == "memory":
        return _build_memory_infra()
    elif config.backend == "redis":
        return _build_redis_infra(config)
    else:
        raise ConfigurationError(f"Unsupported backend: {config.backend}")


def _build_memory_infra() -> InfraBundle:
    """Build in-memory infrastructure backends."""
    from .memory import MemoryDebounce, MemoryRateLimiter

    return InfraBundle(
        rate_limiter=MemoryRateLimiter(),
        debounce=MemoryDebounce(),
    )


def _build_redis_infra(config: SentinelConfig) -> InfraBundle:
    """Build Redis infrastructure backends."""
    try:
        from redis.asyncio import Redis
    except ImportError as e:
        raise ConfigurationError(
            "Redis backend requires redis package. Install with: pip install redis"
        ) from e

    from .redis import RedisDebounce, RedisRateLimiter

    try:
        # Create Redis connection
        redis: Redis = Redis.from_url(config.redis_url)  # type: ignore

        return InfraBundle(
            rate_limiter=RedisRateLimiter(redis, config.redis_prefix),
            debounce=RedisDebounce(redis, config.redis_prefix),
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to create Redis connection: {e}") from e
