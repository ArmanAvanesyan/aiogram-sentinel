"""Key utilities for aiogram-sentinel."""

from __future__ import annotations

import hashlib
import logging
import warnings
from typing import Any

from ..scopes import KeyBuilder

logger = logging.getLogger(__name__)

# Module-level KeyBuilder instance for deprecated functions
_default_key_builder = KeyBuilder(app="sentinel")


def rate_key(user_id: int, handler_name: str, **kwargs: Any) -> str:
    """Build rate limiting key from user ID and handler scope.

    .. deprecated:: 1.1.0
        Use :class:`KeyBuilder` instead. This function will be removed in v2.0.0.

        Migration:
        .. code-block:: python

            # Old
            key = rate_key(user_id, handler_name, **kwargs)

            # New
            from aiogram_sentinel import KeyBuilder
            kb = KeyBuilder(app="sentinel")
            key = kb.user("throttle", user_id, bucket=handler_name, **kwargs)
    """
    # Emit deprecation warning
    warnings.warn(
        "rate_key() is deprecated and will be removed in v2.0.0. "
        "Use KeyBuilder instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Log deprecation warning once
    logger.warning(
        "rate_key() is deprecated and will be removed in v2.0.0. "
        "Use KeyBuilder instead."
    )

    # Create a stable key from user_id and handler_name (original implementation)
    key_parts = [str(user_id), handler_name]

    # Add any additional scope parameters
    for key, value in sorted(kwargs.items()):
        key_parts.append(f"{key}:{value}")

    return ":".join(key_parts)


def debounce_key(user_id: int, handler_name: str, **kwargs: Any) -> str:
    """Build debounce key from user ID and handler scope.

    .. deprecated:: 1.1.0
        Use :class:`KeyBuilder` instead. This function will be removed in v2.0.0.

        Migration:
        .. code-block:: python

            # Old
            key = debounce_key(user_id, handler_name, **kwargs)

            # New
            from aiogram_sentinel import KeyBuilder
            kb = KeyBuilder(app="sentinel")
            key = kb.user("debounce", user_id, bucket=handler_name, **kwargs)
    """
    # Emit deprecation warning
    warnings.warn(
        "debounce_key() is deprecated and will be removed in v2.0.0. "
        "Use KeyBuilder instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Log deprecation warning once
    logger.warning(
        "debounce_key() is deprecated and will be removed in v2.0.0. "
        "Use KeyBuilder instead."
    )

    # Create a stable key from user_id and handler_name (original implementation)
    key_parts = [str(user_id), handler_name]

    # Add any additional scope parameters
    for key, value in sorted(kwargs.items()):
        key_parts.append(f"{key}:{value}")

    return ":".join(key_parts)


def handler_scope(handler_name: str, **kwargs: Any) -> str:
    """Build handler scope string for consistent key generation."""
    scope_parts = [handler_name]

    # Add any additional scope parameters
    for key, value in sorted(kwargs.items()):
        scope_parts.append(f"{key}:{value}")

    return ":".join(scope_parts)


def fingerprint(text: str | None) -> str:
    """Create a stable fingerprint for text content."""
    # Handle None, empty strings, and non-string types
    if not text:
        text = ""
    else:
        text = str(text)

    return hashlib.sha256(text.encode()).hexdigest()[:16]


def user_key(user_id: int) -> str:
    """Build user key from user ID."""
    return str(user_id)


def blocklist_key() -> str:
    """Build blocklist key (global, not user-specific)."""
    return "blocklist"
