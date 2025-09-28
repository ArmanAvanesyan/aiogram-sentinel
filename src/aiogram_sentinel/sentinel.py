"""Main setup helper for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Dispatcher, Router

from .config import SentinelConfig
from .middlewares.auth import AuthMiddleware
from .middlewares.blocking import BlockingMiddleware
from .middlewares.debouncing import DebounceMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .routers.my_chat_member import make_sentinel_router
from .storage.factory import build_backends
from .types import BackendsBundle


class Sentinel:
    """Main setup class for aiogram-sentinel."""

    @staticmethod
    async def setup(
        dp: Dispatcher,
        cfg: SentinelConfig,
        router: Router | None = None,
    ) -> tuple[Router, BackendsBundle]:
        """Setup aiogram-sentinel with all middlewares and router.

        Args:
            dp: aiogram Dispatcher instance
            cfg: SentinelConfig configuration
            router: Optional custom router (if None, creates default)

        Returns:
            Tuple of (router, backends) for further customization
        """
        # Build backends
        backends = build_backends(cfg)

        # Create or use provided router
        if router is None:
            router = Router(name="sentinel")

        # Create middlewares in correct order
        blocking_middleware = BlockingMiddleware(backends.blocklist)
        auth_middleware = AuthMiddleware(backends.user_repo)
        debounce_middleware = DebounceMiddleware(backends.debounce, cfg)
        throttling_middleware = ThrottlingMiddleware(backends.rate_limiter, cfg)

        # Add middlewares to router in correct order
        for reg in (router.message, router.callback_query):
            reg.middleware(blocking_middleware)
            reg.middleware(auth_middleware)
            reg.middleware(debounce_middleware)
            reg.middleware(throttling_middleware)

        # Include membership router for auto block/unblock
        dp.include_router(make_sentinel_router(backends.blocklist))
        dp.include_router(router)

        return router, backends

    @staticmethod
    def add_hooks(
        router: Router,
        backends: BackendsBundle,
        cfg: SentinelConfig,
        *,
        on_rate_limited: Callable[[Any, dict[str, Any], float], Awaitable[Any]]
        | None = None,
        resolve_user: Callable[[Any, dict[str, Any]], Awaitable[dict[str, Any] | None]]
        | None = None,
        on_block: Callable[[int, str, dict[str, Any]], Awaitable[Any]] | None = None,
        on_unblock: Callable[[int, str, dict[str, Any]], Awaitable[Any]] | None = None,
    ) -> None:
        """Add hooks to existing middlewares.

        Args:
            router: Router with middlewares
            backends: Backends bundle
            cfg: SentinelConfig configuration
            on_rate_limited: Optional hook for rate-limited events
            resolve_user: Optional hook for user resolution
            on_block: Optional hook for block events
            on_unblock: Optional hook for unblock events
        """
        # Create middlewares with hooks
        auth_middleware = AuthMiddleware(backends.user_repo, resolve_user=resolve_user)
        throttling_middleware = ThrottlingMiddleware(
            backends.rate_limiter, cfg, on_rate_limited=on_rate_limited
        )

        # Replace middlewares with hook-enabled versions
        for reg in (router.message, router.callback_query):
            # Remove existing middlewares and add new ones
            # Note: This is a simplified approach - in practice, you might want
            # to replace specific middlewares or use a different pattern
            reg.middleware(auth_middleware)
            reg.middleware(throttling_middleware)

        # Update membership router with hooks
        # Note: This would require re-including the router with hooks
        # In practice, you might want to create a new router with hooks


async def setup_sentinel(
    dp: Dispatcher,
    cfg: SentinelConfig,
    router: Router | None = None,
) -> tuple[Router, BackendsBundle]:
    """Convenience function for Sentinel.setup.

    Args:
        dp: aiogram Dispatcher instance
        cfg: SentinelConfig configuration
        router: Optional custom router

    Returns:
        Tuple of (router, backends)
    """
    return await Sentinel.setup(dp, cfg, router)
