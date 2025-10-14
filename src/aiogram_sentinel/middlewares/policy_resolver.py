"""Policy resolver middleware for aiogram-sentinel."""

from __future__ import annotations

import logging
import warnings
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..config import SentinelConfig
from ..policy import (
    DebounceCfg,
    PolicyRegistry,
    ThrottleCfg,
    convert_from_legacy_debounce,
    convert_from_legacy_throttle,
)

logger = logging.getLogger(__name__)


class PolicyResolverMiddleware(BaseMiddleware):
    """Middleware that resolves policies and legacy decorators into configuration."""

    def __init__(
        self,
        registry: PolicyRegistry,
        cfg: SentinelConfig,
    ) -> None:
        """Initialize the policy resolver middleware.

        Args:
            registry: Policy registry instance
            cfg: SentinelConfig configuration
        """
        super().__init__()
        self._registry = registry
        self._cfg = cfg

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process the event through policy resolution."""
        # Resolve policies and legacy decorators
        throttle_cfg, debounce_cfg = self._resolve_configurations(handler)

        # Inject resolved configurations into data
        if throttle_cfg is not None:
            data["sentinel_throttle_cfg"] = throttle_cfg

        if debounce_cfg is not None:
            data["sentinel_debounce_cfg"] = debounce_cfg

        # Continue to next middleware/handler
        return await handler(event, data)

    def _resolve_configurations(
        self, handler: Callable[..., Any]
    ) -> tuple[ThrottleCfg | None, DebounceCfg | None]:
        """Resolve throttling and debouncing configurations.

        Args:
            handler: Handler function

        Returns:
            Tuple of (throttle_cfg, debounce_cfg)
        """
        throttle_cfg = None
        debounce_cfg = None

        # Process policies (later overrides earlier for same kind)
        if hasattr(handler, "__sentinel_policies__"):
            policy_names = handler.__sentinel_policies__  # type: ignore

            for policy_name in policy_names:
                try:
                    policy = self._registry.get(policy_name)

                    if policy.kind == "throttle":
                        throttle_cfg = policy.cfg
                    elif policy.kind == "debounce":
                        debounce_cfg = policy.cfg

                except ValueError as e:
                    # Re-raise with more context
                    raise ValueError(
                        f"Failed to resolve policy '{policy_name}' for handler "
                        f"'{getattr(handler, '__name__', 'unknown')}': {e}"
                    ) from e

        # Check legacy decorators
        if hasattr(handler, "sentinel_rate_limit"):
            if throttle_cfg is not None:
                warnings.warn(
                    "Both @policy and @rate_limit found on handler "
                    f"'{getattr(handler, '__name__', 'unknown')}'; "
                    "@rate_limit is deprecated and will be ignored",
                    DeprecationWarning,
                    stacklevel=2,
                )
            else:
                try:
                    throttle_cfg = convert_from_legacy_throttle(
                        handler.sentinel_rate_limit  # type: ignore
                    )
                except ValueError as e:
                    logger.warning(
                        "Failed to convert legacy throttling config for handler "
                        f"'{getattr(handler, '__name__', 'unknown')}': {e}"
                    )

        if hasattr(handler, "sentinel_debounce"):
            if debounce_cfg is not None:
                warnings.warn(
                    "Both @policy and @debounce found on handler "
                    f"'{getattr(handler, '__name__', 'unknown')}'; "
                    "@debounce is deprecated and will be ignored",
                    DeprecationWarning,
                    stacklevel=2,
                )
            else:
                try:
                    debounce_cfg = convert_from_legacy_debounce(
                        handler.sentinel_debounce  # type: ignore
                    )
                except ValueError as e:
                    logger.warning(
                        "Failed to convert legacy debouncing config for handler "
                        f"'{getattr(handler, '__name__', 'unknown')}': {e}"
                    )

        return throttle_cfg, debounce_cfg
