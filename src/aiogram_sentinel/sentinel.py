"""Main setup helper for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

from aiogram import Dispatcher, Router
from aiogram.types import TelegramObject

from .config import SentinelConfig
from .exceptions import ConfigurationError
from .middlewares.debouncing import DebounceMiddleware
from .middlewares.errors import ErrorConfig, ErrorHandlingMiddleware
from .middlewares.policy_resolver import PolicyResolverMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .policy import registry
from .scopes import KeyBuilder
from .storage.factory import build_infra
from .types import InfraBundle

RateLimitHook = Callable[[TelegramObject, dict[str, Any], float], Awaitable[None]]


@dataclass
class _Hook:
    callback: RateLimitHook | None = None

    async def __call__(
        self, event: TelegramObject, data: dict[str, Any], retry_after: float
    ) -> None:
        if self.callback is not None:
            await self.callback(event, data, retry_after)


@dataclass
class _Installation:
    infra: InfraBundle
    cfg: SentinelConfig
    hook: _Hook


_installations: WeakKeyDictionary[Router, _Installation] = WeakKeyDictionary()


class Sentinel:
    """Main setup class for aiogram-sentinel."""

    _error_config: ErrorConfig | None = None

    @staticmethod
    async def setup(
        dp: Dispatcher,
        cfg: SentinelConfig,
        router: Router | None = None,
        *,
        infra: InfraBundle | None = None,
        error_config: ErrorConfig | None = None,
    ) -> tuple[Router, InfraBundle]:
        """Setup aiogram-sentinel middlewares.

        Args:
            dp: Dispatcher instance
            cfg: Configuration
            router: Optional router to use (creates new one if not provided)
            infra: Optional infrastructure bundle (builds from config if not provided)
            error_config: Optional error handling configuration

        Returns:
            Tuple of (router, infra_bundle)
        """
        if router is not None and (
            router in _installations or router.parent_router is not None
        ):
            raise ConfigurationError("Router is already installed or attached")

        # Build infrastructure if not provided
        if infra is None:
            infra = build_infra(cfg)

        # Create KeyBuilder instance
        key_builder = KeyBuilder(app=cfg.redis_prefix)

        # Create or use provided router
        if router is None:
            router = Router(name="sentinel")

        # Create middlewares in correct order with KeyBuilder
        policy_resolver = PolicyResolverMiddleware(registry, cfg)
        debounce_middleware = DebounceMiddleware(infra.debounce, cfg, key_builder)
        hook = _Hook()
        throttling_middleware = ThrottlingMiddleware(
            infra.rate_limiter, cfg, key_builder, on_rate_limited=hook
        )

        # Create error handling middleware if configured
        error_middleware = None
        effective_error_config = error_config or Sentinel._error_config
        if effective_error_config:
            error_middleware = ErrorHandlingMiddleware(
                effective_error_config, key_builder, infra.rate_limiter
            )

        # Add middlewares to router in correct order
        for reg in (router.message, router.callback_query):
            if error_middleware:
                reg.middleware(error_middleware)  # FIRST (outermost)
            reg.middleware(policy_resolver)
            reg.middleware(debounce_middleware)
            reg.middleware(throttling_middleware)

        # Include router in dispatcher
        dp.include_router(router)
        _installations[router] = _Installation(infra, cfg, hook)
        Sentinel._error_config = None

        return router, infra

    @staticmethod
    def use_errors(error_config: ErrorConfig) -> None:
        """Configure error handling for the next setup call.

        Args:
            error_config: Error handling configuration
        """
        # This is a convenience method that can be used to configure
        # error handling before calling setup()
        Sentinel._error_config = error_config

    @staticmethod
    def add_hooks(
        router: Router,
        infra: InfraBundle,
        cfg: SentinelConfig,
        *,
        on_rate_limited: RateLimitHook | None = None,
    ) -> None:
        """Update this router's owned hook without replacing any middleware.

        The router, infrastructure and configuration must come from the same
        successful ``setup`` call. Passing ``None`` removes the hook.
        """
        installation = _installations.get(router)
        if installation is None:
            raise ConfigurationError("Router was not installed by Sentinel.setup")
        if installation.infra is not infra or installation.cfg is not cfg:
            raise ConfigurationError(
                "Hook configuration does not match router installation"
            )
        installation.hook.callback = on_rate_limited


async def setup_sentinel(
    dp: Dispatcher,
    cfg: SentinelConfig,
    router: Router | None = None,
    *,
    infra: InfraBundle | None = None,
) -> tuple[Router, InfraBundle]:
    """Convenience function for Sentinel.setup.

    Args:
        dp: Dispatcher instance
        cfg: Configuration
        router: Optional router to use (creates new one if not provided)
        infra: Optional infrastructure bundle (builds from config if not provided)

    Returns:
        Tuple of (router, infra_bundle)
    """
    return await Sentinel.setup(dp, cfg, router, infra=infra)
