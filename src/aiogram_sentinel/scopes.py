"""Scope enum and composite KeyBuilder for unified key generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class Scope(Enum):
    """Scope enumeration for key generation."""

    USER = auto()
    CHAT = auto()
    GROUP = auto()  # user+chat composite
    GLOBAL = auto()


@dataclass(frozen=True)
class KeyParts:
    """Immutable key parts for consistent key generation."""

    namespace: str
    scope: Scope
    identifiers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate key parts after initialization."""
        if not self.namespace:
            raise ValueError("namespace cannot be empty")
        if not self.identifiers:
            raise ValueError("identifiers cannot be empty")

        # Validate identifiers don't contain separator characters
        for identifier in self.identifiers:
            if not identifier:
                raise ValueError("identifier cannot be empty")
            if ":" in identifier:
                raise ValueError(
                    f"identifier cannot contain separator ':': {identifier}"
                )


class KeyBuilder:
    """Composite key builder with collision-proof scheme."""

    def __init__(self, app: str, sep: str = ":") -> None:
        """Initialize KeyBuilder.

        Args:
            app: Application prefix (typically from redis_prefix config)
            sep: Key separator character
        """
        if not app:
            raise ValueError("app cannot be empty")
        if sep in app:
            raise ValueError(f"app cannot contain separator '{sep}': {app}")

        self.app = app
        self.sep = sep

    def for_update(
        self,
        parts: KeyParts,
        *,
        method: str | None = None,
        bucket: str | None = None,
    ) -> str:
        """Build canonical key for storage/metrics with stable ordering.

        Args:
            parts: Key parts containing namespace, scope, and identifiers
            method: Optional method name (e.g., "sendMessage")
            bucket: Optional bucket identifier

        Returns:
            Canonical key string

        Raises:
            ValueError: If method or bucket contain separator characters
        """
        # Validate optional parameters
        if method is not None and self.sep in method:
            raise ValueError(f"method cannot contain separator '{self.sep}': {method}")
        if bucket is not None and self.sep in bucket:
            raise ValueError(f"bucket cannot contain separator '{self.sep}': {bucket}")

        # Build key components
        key_parts = [self.app, parts.namespace, parts.scope.name]

        # Add identifiers
        key_parts.extend(parts.identifiers)

        # Add optional method parameter
        if method is not None:
            key_parts.append(f"m={method}")

        # Add optional bucket parameter
        if bucket is not None:
            key_parts.append(f"b={bucket}")

        return self.sep.join(key_parts)

    def user(self, namespace: str, user_id: int, **kwargs: Any) -> str:
        """Build key for user scope.

        Args:
            namespace: Key namespace (e.g., "throttle", "debounce")
            user_id: User identifier
            **kwargs: Additional parameters (method, bucket)

        Returns:
            User-scoped key
        """
        parts = KeyParts(
            namespace=namespace, scope=Scope.USER, identifiers=(str(user_id),)
        )
        return self.for_update(parts, **kwargs)

    def chat(self, namespace: str, chat_id: int, **kwargs: Any) -> str:
        """Build key for chat scope.

        Args:
            namespace: Key namespace (e.g., "throttle", "debounce")
            chat_id: Chat identifier
            **kwargs: Additional parameters (method, bucket)

        Returns:
            Chat-scoped key
        """
        parts = KeyParts(
            namespace=namespace, scope=Scope.CHAT, identifiers=(str(chat_id),)
        )
        return self.for_update(parts, **kwargs)

    def group(self, namespace: str, user_id: int, chat_id: int, **kwargs: Any) -> str:
        """Build key for group scope (user+chat composite).

        Args:
            namespace: Key namespace (e.g., "throttle", "debounce")
            user_id: User identifier
            chat_id: Chat identifier
            **kwargs: Additional parameters (method, bucket)

        Returns:
            Group-scoped key
        """
        parts = KeyParts(
            namespace=namespace,
            scope=Scope.GROUP,
            identifiers=(str(user_id), str(chat_id)),
        )
        return self.for_update(parts, **kwargs)

    def global_(self, namespace: str, **kwargs: Any) -> str:
        """Build key for global scope.

        Args:
            namespace: Key namespace (e.g., "throttle", "debounce")
            **kwargs: Additional parameters (method, bucket)

        Returns:
            Global-scoped key
        """
        parts = KeyParts(
            namespace=namespace, scope=Scope.GLOBAL, identifiers=("global",)
        )
        return self.for_update(parts, **kwargs)
