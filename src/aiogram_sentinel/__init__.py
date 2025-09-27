"""aiogram-sentinel: Edge hygiene library for aiogram v3."""

from .config import SentinelConfig
from .decorators import debounce, rate_limit, require_registered
from .middlewares.auth import AuthMiddleware
from .middlewares.blocking import BlockingMiddleware
from .middlewares.debouncing import DebounceMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .routers.my_chat_member import make_sentinel_router
from .sentinel import Sentinel, setup_sentinel
from .storage.base import (
    BlocklistBackend,
    DebounceBackend,
    RateLimiterBackend,
    UserRepo,
)
from .storage.factory import build_backends
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
    "Sentinel",
    "setup_sentinel",
    "build_backends",
    "make_sentinel_router",
    "BlockingMiddleware",
    "AuthMiddleware",
    "DebounceMiddleware",
    "ThrottlingMiddleware",
    "rate_limit",
    "debounce",
    "require_registered",
]
