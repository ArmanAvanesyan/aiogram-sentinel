"""aiogram-sentinel: Rate limiting and debouncing middleware for aiogram bots."""

from .config import SentinelConfig
from .decorators import debounce, rate_limit
from .middlewares.debouncing import DebounceMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .sentinel import Sentinel, setup_sentinel
from .storage.base import DebounceBackend, RateLimiterBackend
from .storage.factory import build_infra
from .types import InfraBundle
from .version import __version__

__all__: list[str] = [
    "__version__",
    "SentinelConfig",
    "InfraBundle",
    "RateLimiterBackend",
    "DebounceBackend",
    "Sentinel",
    "setup_sentinel",
    "build_infra",
    "DebounceMiddleware",
    "ThrottlingMiddleware",
    "rate_limit",
    "debounce",
]
