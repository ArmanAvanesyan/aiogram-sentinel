"""Main setup helper for aiogram-sentinel."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

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
    def setup(
        dp: Dispatcher,
        cfg: SentinelConfig,
        router: Optional[Router] = None,
        on_rate_limited: Optional[Callable[[Any, Dict[str, Any], float], Awaitable[Any]]] = None,
        resolve_user: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]]] = None,
        on_block: Optional[Callable[[int, str, Dict[str, Any]], Awaitable[Any]]] = None,
        on_unblock: Optional[Callable[[int, str, Dict[str, Any]], Awaitable[Any]]] = None,
    ) -> Tuple[Router, BackendsBundle]:
        """Setup aiogram-sentinel with all middlewares and router.
        
        Args:
            dp: aiogram Dispatcher instance
            cfg: SentinelConfig configuration
            router: Optional custom router (if None, creates default)
            on_rate_limited: Optional hook for rate-limited events
            resolve_user: Optional hook for user resolution
            on_block: Optional hook for block events
            on_unblock: Optional hook for unblock events
            
        Returns:
            Tuple of (router, backends) for further customization
        """
        # Build backends
        backends = build_backends(cfg)
        
        # Create middlewares in correct order
        blocking_middleware = BlockingMiddleware(backends.blocklist)
        auth_middleware = AuthMiddleware(backends.user_repo, resolve_user=resolve_user)
        debounce_middleware = DebounceMiddleware(backends.debounce, cfg.default_debounce_delay)
        throttling_middleware = ThrottlingMiddleware(
            backends.rate_limiter,
            cfg.default_rate_limit,
            cfg.default_rate_window,
            on_rate_limited=on_rate_limited,
        )
        
        # Add middlewares to dispatcher in correct order
        dp.message.middleware(blocking_middleware)
        dp.message.middleware(auth_middleware)
        dp.message.middleware(debounce_middleware)
        dp.message.middleware(throttling_middleware)
        
        dp.callback_query.middleware(blocking_middleware)
        dp.callback_query.middleware(auth_middleware)
        dp.callback_query.middleware(debounce_middleware)
        dp.callback_query.middleware(throttling_middleware)
        
        # Create or use provided router
        if router is None:
            router = make_sentinel_router(
                backends.blocklist,
                on_block=on_block,
                on_unblock=on_unblock,
            )
        
        # Include router in dispatcher
        dp.include_router(router)
        
        return router, backends


def setup_sentinel(
    dp: Dispatcher,
    cfg: SentinelConfig,
    router: Optional[Router] = None,
    **kwargs: Any,
) -> Tuple[Router, BackendsBundle]:
    """Convenience function for Sentinel.setup.
    
    Args:
        dp: aiogram Dispatcher instance
        cfg: SentinelConfig configuration
        router: Optional custom router
        **kwargs: Additional arguments passed to Sentinel.setup
        
    Returns:
        Tuple of (router, backends)
    """
    return Sentinel.setup(dp, cfg, router, **kwargs)
