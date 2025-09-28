"""Storage backend implementations for aiogram-sentinel."""

from .base import (
    BlocklistBackend,
    DebounceBackend,
    RateLimiterBackend,
    UserRepo,
)
from .factory import build_backends
from .memory import (
    MemoryBlocklist,
    MemoryDebounce,
    MemoryRateLimiter,
    MemoryUserRepo,
)
from .redis import (
    RedisBlocklist,
    RedisDebounce,
    RedisRateLimiter,
    RedisUserRepo,
)

__all__ = [
    # Protocols
    "BlocklistBackend",
    "DebounceBackend",
    "RateLimiterBackend",
    "UserRepo",
    # Factory
    "build_backends",
    # Memory implementations
    "MemoryBlocklist",
    "MemoryDebounce",
    "MemoryRateLimiter",
    "MemoryUserRepo",
    # Redis implementations
    "RedisBlocklist",
    "RedisDebounce",
    "RedisRateLimiter",
    "RedisUserRepo",
]
