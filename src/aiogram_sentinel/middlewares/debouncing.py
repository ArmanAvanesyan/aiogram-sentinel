"""Debouncing middleware for aiogram-sentinel."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..config import SentinelConfig
from ..context import extract_group_ids, extract_handler_bucket
from ..policy import DebounceCfg, resolve_scope
from ..scopes import KeyBuilder, Scope
from ..storage.base import DebounceBackend
from ..utils.keys import fingerprint

logger = logging.getLogger(__name__)


class DebounceMiddleware(BaseMiddleware):
    """Middleware for debouncing duplicate messages with fingerprinting."""

    def __init__(
        self,
        debounce_backend: DebounceBackend,
        cfg: SentinelConfig,
        key_builder: KeyBuilder,
    ) -> None:
        """Initialize the debouncing middleware.

        Args:
            debounce_backend: Debounce backend instance
            cfg: SentinelConfig configuration
            key_builder: KeyBuilder instance for key generation
        """
        super().__init__()
        self._debounce_backend = debounce_backend
        self._cfg = cfg
        self._key_builder = key_builder
        self._default_delay = cfg.debounce_default_window

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process the event through debouncing middleware."""
        # Get debounce configuration
        window_seconds = self._get_debounce_window(handler, data, event)

        # Generate fingerprint for the event
        fp = self._generate_fingerprint(event)

        # Generate debounce key
        key = self._generate_debounce_key(event, handler, data)

        # Check if already seen within window
        if await self._debounce_backend.seen(key, window_seconds, fp):
            # Duplicate detected within window
            data["sentinel_debounced"] = True
            return  # Stop processing

        # Continue to next middleware/handler
        return await handler(event, data)

    def _get_debounce_window(
        self, handler: Callable[..., Any], data: dict[str, Any], event: TelegramObject | None = None
    ) -> int:
        """Get debounce window from handler or use default."""
        # Check for policy-based configuration first
        if "sentinel_debounce_cfg" in data:
            cfg = data["sentinel_debounce_cfg"]
            if isinstance(cfg, DebounceCfg):
                # Check if scope cap can be satisfied
                from ..context import extract_group_ids
                user_id, chat_id = extract_group_ids(event or data.get("event"), data)
                resolved_scope = resolve_scope(user_id, chat_id, cfg.scope)

                if resolved_scope is None:
                    # Scope cap cannot be satisfied, skip policy config
                    logger.debug(
                        "Policy skipped: required scope identifiers missing",
                        extra={
                            "cap": cfg.scope.value if cfg.scope else None,
                            "user_id": user_id,
                            "chat_id": chat_id,
                            "handler": getattr(handler, "__name__", "unknown"),
                        },
                    )
                    # Fall through to check other config sources
                else:
                    return cfg.window

        # Check if handler has debounce configuration
        if hasattr(handler, "sentinel_debounce"):  # type: ignore
            config = handler.sentinel_debounce  # type: ignore
            if isinstance(config, (tuple, list)) and len(config) >= 1:  # type: ignore
                return int(config[0])  # type: ignore
            elif isinstance(config, dict):
                delay = config.get("delay", self._cfg.debounce_default_window)  # type: ignore
                return int(delay)  # type: ignore

        # Check data for debounce configuration
        if "sentinel_debounce" in data:
            config = data["sentinel_debounce"]
            if isinstance(config, tuple) and len(config) >= 1:  # type: ignore
                return int(config[0])  # type: ignore

        # Use default
        return self._cfg.debounce_default_window

    def _generate_fingerprint(self, event: TelegramObject) -> str:
        """Generate SHA256 fingerprint for event content."""
        content = self._extract_content(event)

        if not content:
            # Fallback to hashed representation of the entire event
            content = str(event)

        return fingerprint(content)

    def _extract_content(self, event: TelegramObject) -> str:
        """Extract content from event for fingerprinting."""
        # Try to get text from message
        if hasattr(event, "text") and getattr(event, "text", None):  # type: ignore
            return event.text  # type: ignore

        # Try to get caption from message
        if hasattr(event, "caption") and getattr(event, "caption", None):  # type: ignore
            return event.caption  # type: ignore

        # Try to get data from callback query
        if hasattr(event, "data") and getattr(event, "data", None):  # type: ignore
            return event.data  # type: ignore

        # Try to get query from inline query
        if hasattr(event, "query") and getattr(event, "query", None):  # type: ignore
            return event.query  # type: ignore

        # Return empty string if no content found
        return ""

    def _generate_debounce_key(
        self,
        event: TelegramObject,
        handler: Callable[..., Any],
        data: dict[str, Any],
    ) -> str:
        """Generate debounce key for the event using KeyBuilder."""
        # Extract user and chat IDs using context extractors
        user_id, chat_id = extract_group_ids(event, data)

        # Auto-extract bucket from handler
        bucket = extract_handler_bucket(event, data)

        # Get handler name as fallback bucket
        if bucket is None:
            bucket = getattr(handler, "__name__", "unknown")

        # Get additional parameters from policy config, handler config, or data
        method = None
        explicit_bucket = None
        scope_cap = None

        # Check policy-based configuration first
        if "sentinel_debounce_cfg" in data:
            cfg = data["sentinel_debounce_cfg"]
            if isinstance(cfg, DebounceCfg):
                method = cfg.method
                explicit_bucket = cfg.bucket
                scope_cap = cfg.scope

        # Check handler configuration for overrides (if no policy config)
        if method is None and explicit_bucket is None and scope_cap is None:
            if hasattr(handler, "sentinel_debounce"):
                config = handler.sentinel_debounce  # type: ignore
                if isinstance(config, dict):
                    method = config.get("method")  # type: ignore
                    explicit_bucket = config.get("bucket")  # type: ignore

        # Check data for overrides
        if "sentinel_method" in data:
            method = data["sentinel_method"]
        if "sentinel_bucket" in data:
            explicit_bucket = data["sentinel_bucket"]

        # Use explicit bucket if provided, otherwise use auto-extracted
        final_bucket = explicit_bucket if explicit_bucket is not None else bucket

        # Resolve scope with cap constraint
        resolved_scope = resolve_scope(user_id, chat_id, scope_cap)
        if resolved_scope is None:
            # Cannot satisfy scope cap - log debug and skip debouncing
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(
                "Policy skipped: required scope identifiers missing",
                extra={
                    "cap": scope_cap.value if scope_cap else None,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "handler": getattr(handler, "__name__", "unknown"),
                },
            )
            # Return a dummy key that will pass debouncing
            return self._key_builder.global_(
                "debounce", method=method, bucket=final_bucket
            )

        # Build key based on resolved scope
        if (
            resolved_scope == Scope.GROUP
            and user_id is not None
            and chat_id is not None
        ):
            return self._key_builder.group(
                "debounce", user_id, chat_id, method=method, bucket=final_bucket
            )
        elif resolved_scope == Scope.USER and user_id is not None:
            return self._key_builder.user(
                "debounce", user_id, method=method, bucket=final_bucket
            )
        elif resolved_scope == Scope.CHAT and chat_id is not None:
            return self._key_builder.chat(
                "debounce", chat_id, method=method, bucket=final_bucket
            )
        else:  # Scope.GLOBAL
            return self._key_builder.global_(
                "debounce", method=method, bucket=final_bucket
            )
