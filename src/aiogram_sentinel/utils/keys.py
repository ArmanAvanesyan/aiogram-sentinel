"""Key utilities for aiogram-sentinel."""

from __future__ import annotations

import hashlib
from typing import Any


def rate_key(user_id: int, handler_name: str, **kwargs: Any) -> str:
    """Build rate limiting key from user ID and handler scope."""
    # Create a stable key from user_id and handler_name
    key_parts = [str(user_id), handler_name]

    # Add any additional scope parameters
    for key, value in sorted(kwargs.items()):
        key_parts.append(f"{key}:{value}")

    return ":".join(key_parts)


def debounce_key(user_id: int, handler_name: str, **kwargs: Any) -> str:
    """Build debounce key from user ID and handler scope."""
    # Create a stable key from user_id and handler_name
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


def fingerprint(text: str) -> str:
    """Create a stable fingerprint for text content."""
    # Handle None, empty strings, and non-string types
    if not text or not isinstance(text, str):
        text = str(text) if text is not None else ""

    return hashlib.sha256(text.encode()).hexdigest()[:16]


def user_key(user_id: int) -> str:
    """Build user key from user ID."""
    return str(user_id)


def blocklist_key() -> str:
    """Build blocklist key (global, not user-specific)."""
    return "blocklist"
