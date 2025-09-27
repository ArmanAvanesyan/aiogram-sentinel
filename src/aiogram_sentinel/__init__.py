"""aiogram-sentinel: Edge hygiene library for aiogram v3."""

from .config import SentinelConfig
from .storage.base import (
    BlocklistBackend,
    DebounceBackend,
    RateLimiterBackend,
    UserRepo,
)
from .types import BackendsBundle
from .version import __version__

__all__: list[str] = [
    "__version__",
    "SentinelConfig",
    "BackendsBundle",
    "RateLimiterBackend",
    "DebounceBackend",
    "BlocklistBackend",
    "UserRepo",
]
