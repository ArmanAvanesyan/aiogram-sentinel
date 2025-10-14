"""Main setup helper for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Dispatcher, Router

from .config import SentinelConfig
from .middlewares.debouncing import DebounceMiddleware
from .middlewares.errors import ErrorConfig, ErrorHandlingMiddleware
from .middlewares.policy_resolver import PolicyResolverMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .policy import registry
from .scopes import KeyBuilder
from .storage.factory import build_infra
from .types import InfraBundle


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
        throttling_middleware = ThrottlingMiddleware(
            infra.rate_limiter, cfg, key_builder
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
        on_rate_limited: Callable[[Any, dict[str, Any], float], Awaitable[Any]]
        | None = None,
    ) -> None:
        """Add hooks to existing middlewares.

        Args:
            router: Router with middlewares
            infra: Infrastructure bundle (rate_limiter, debounce)
            cfg: SentinelConfig configuration
            on_rate_limited: Optional hook for rate-limited events
        """
        # Create KeyBuilder instance
        key_builder = KeyBuilder(app=cfg.redis_prefix)

        # Create middlewares with hooks
        policy_resolver = PolicyResolverMiddleware(registry, cfg)
        debounce_middleware = DebounceMiddleware(infra.debounce, cfg, key_builder)
        throttling_middleware = ThrottlingMiddleware(
            infra.rate_limiter, cfg, key_builder, on_rate_limited=on_rate_limited
        )

        # Replace middlewares with hook-enabled versions
        for reg in (router.message, router.callback_query):
            # Clear existing middlewares
            reg.middlewares.clear()  # type: ignore

            # Add complete middleware chain with hooks in correct order
            reg.middleware(policy_resolver)  # FIRST
            reg.middleware(debounce_middleware)
            reg.middleware(throttling_middleware)


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
