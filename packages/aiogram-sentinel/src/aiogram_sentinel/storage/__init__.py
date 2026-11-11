"""Storage implementations; Redis imports are lazy and require the Redis extra."""

from typing import TYPE_CHECKING, Any

from .base import DebounceBackend, RateLimiterBackend
from .factory import build_infra
from .memory import MemoryDebounce, MemoryRateLimiter

if TYPE_CHECKING:
    from .redis import RedisDebounce, RedisRateLimiter

__all__ = [
    "DebounceBackend",
    "RateLimiterBackend",
    "build_infra",
    "MemoryDebounce",
    "MemoryRateLimiter",
    "RedisDebounce",
    "RedisRateLimiter",
]


def __getattr__(name: str) -> Any:
    if name in {"RedisDebounce", "RedisRateLimiter"}:
        from . import redis

        return getattr(redis, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
