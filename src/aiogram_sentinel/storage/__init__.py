"""Storage backend implementations for aiogram-sentinel."""

from .base import (
    DebounceBackend,
    RateLimiterBackend,
)
from .factory import build_infra
from .memory import (
    MemoryDebounce,
    MemoryRateLimiter,
)
from .redis import (
    RedisDebounce,
    RedisRateLimiter,
)

__all__ = [
    # Protocols
    "DebounceBackend",
    "RateLimiterBackend",
    # Factory
    "build_infra",
    # Memory implementations
    "MemoryDebounce",
    "MemoryRateLimiter",
    # Redis implementations
    "RedisDebounce",
    "RedisRateLimiter",
]
