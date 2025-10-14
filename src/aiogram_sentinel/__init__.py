"""aiogram-sentinel: Rate limiting and debouncing middleware for aiogram bots."""

from .config import SentinelConfig
from .decorators import debounce, rate_limit
from .middlewares.debouncing import DebounceMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .policy import (
    DebounceCfg,
    Policy,
    PolicyKind,
    PolicyRegistry,
    ThrottleCfg,
    coerce_scope,
    policy,
    registry,
    resolve_scope,
)
from .scopes import KeyBuilder, KeyParts, Scope
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
    "Scope",
    "KeyParts",
    "KeyBuilder",
    "Policy",
    "PolicyRegistry",
    "PolicyKind",
    "ThrottleCfg",
    "DebounceCfg",
    "policy",
    "registry",
    "coerce_scope",
    "resolve_scope",
]
