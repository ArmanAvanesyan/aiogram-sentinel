"""Policy registry and configuration for aiogram-sentinel."""

from __future__ import annotations

import difflib
import warnings
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .scopes import Scope

PolicyKind = Literal["throttle", "debounce"]


@dataclass(frozen=True)
class ThrottleCfg:
    """Configuration for throttling policy."""

    rate: int
    per: int
    scope: Scope | None = None
    method: str | None = None
    bucket: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.rate <= 0:
            raise ValueError("rate must be positive")
        if self.per <= 0:
            raise ValueError("per must be positive")


@dataclass(frozen=True)
class DebounceCfg:
    """Configuration for debouncing policy."""

    window: int
    scope: Scope | None = None
    method: str | None = None
    bucket: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.window <= 0:
            raise ValueError("window must be positive")


@dataclass(frozen=True)
class Policy:
    """A named policy configuration."""

    name: str
    kind: PolicyKind
    cfg: ThrottleCfg | DebounceCfg
    description: str = ""

    def __post_init__(self) -> None:
        """Validate policy after initialization."""
        if not self.name:
            raise ValueError("policy name cannot be empty")

        # Validate cfg matches kind
        if self.kind == "throttle" and not isinstance(self.cfg, ThrottleCfg):
            raise ValueError("throttle policy must use ThrottleCfg")
        elif self.kind == "debounce" and not isinstance(self.cfg, DebounceCfg):
            raise ValueError("debounce policy must use DebounceCfg")


class PolicyRegistry:
    """Registry for managing named policies."""

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._policies: OrderedDict[str, Policy] = OrderedDict()

    def register(self, policy: Policy) -> None:
        """Register a new policy.

        Args:
            policy: Policy to register

        Raises:
            ValueError: If policy name already exists
        """
        if policy.name in self._policies:
            raise ValueError(f"Policy '{policy.name}' already registered")

        self._policies[policy.name] = policy

    def get(self, name: str) -> Policy:
        """Get policy by name.

        Args:
            name: Policy name

        Returns:
            Policy instance

        Raises:
            ValueError: If policy not found, with suggestions
        """
        if name in self._policies:
            return self._policies[name]

        # Generate suggestions
        suggestions = difflib.get_close_matches(
            name, self._policies.keys(), n=3, cutoff=0.6
        )

        if suggestions:
            suggestion_text = f" Did you mean: {', '.join(suggestions)}?"
        else:
            suggestion_text = ""

        raise ValueError(f"Policy '{name}' not found.{suggestion_text}")

    def all(self) -> list[Policy]:
        """Get all registered policies in registration order.

        Returns:
            List of all policies
        """
        return list(self._policies.values())

    def clear(self) -> None:
        """Clear all registered policies."""
        self._policies.clear()


# Global registry instance
registry = PolicyRegistry()


def coerce_scope(scope: str | Scope | None) -> Scope | None:
    """Coerce string scope to Scope enum with deprecation warning.

    Args:
        scope: String, Scope enum, or None

    Returns:
        Scope enum or None

    Raises:
        ValueError: If string scope is invalid
    """
    if isinstance(scope, str):
        warnings.warn(
            "String scope is deprecated, use Scope enum",
            DeprecationWarning,
            stacklevel=3,
        )
        try:
            return Scope[scope.upper()]
        except KeyError:
            raise ValueError(f"Invalid scope: {scope}") from None

    return scope


def resolve_scope(
    user_id: int | None, chat_id: int | None, cap: Scope | None
) -> Scope | None:
    """Resolve scope with cap constraint.

    Args:
        user_id: User identifier
        chat_id: Chat identifier
        cap: Maximum scope allowed (cap constraint)

    Returns:
        Resolved scope or None if cannot satisfy cap
    """
    # Determine available scopes
    available: set[Scope] = set()
    if user_id and chat_id:
        available.add(Scope.GROUP)
    if user_id:
        available.add(Scope.USER)
    if chat_id:
        available.add(Scope.CHAT)
    available.add(Scope.GLOBAL)

    # Specificity order (most specific first)
    order = [Scope.USER, Scope.CHAT, Scope.GROUP, Scope.GLOBAL]

    # Filter by cap if provided
    if cap:
        cap_idx = order.index(cap)
        candidates = order[: cap_idx + 1]
    else:
        candidates = order

    # Return first available in specificity order
    for s in candidates:
        if s in available:
            return s

    return None


def policy(*names: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to attach policies to handlers.

    Args:
        *names: Policy names to attach

    Returns:
        Decorator function

    Raises:
        ValueError: If no policy names provided
    """
    if not names:
        raise ValueError("At least one policy name must be provided")

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        """Attach policies to handler."""
        handler.__sentinel_policies__ = names  # type: ignore
        return handler

    return decorator


def convert_from_legacy_throttle(
    config: tuple[Any, ...] | dict[str, Any],
) -> ThrottleCfg:
    """Convert legacy throttling config to ThrottleCfg.

    Args:
        config: Legacy config tuple or dict

    Returns:
        ThrottleCfg instance
    """
    if isinstance(config, (tuple, list)) and len(config) >= 2:
        rate, per = config[0], config[1]
        scope_str = config[2] if len(config) > 2 else None
        scope = coerce_scope(scope_str) if scope_str else None
        return ThrottleCfg(rate=rate, per=per, scope=scope)
    elif isinstance(config, dict):
        rate = config.get("limit", config.get("rate", 5))
        per = config.get("window", config.get("per", 10))
        scope_str = config.get("scope")
        scope = coerce_scope(scope_str) if scope_str else None
        method = config.get("method")
        bucket = config.get("bucket")
        return ThrottleCfg(
            rate=rate, per=per, scope=scope, method=method, bucket=bucket
        )
    else:
        raise ValueError(f"Invalid legacy throttling config: {config}")


def convert_from_legacy_debounce(
    config: tuple[Any, ...] | dict[str, Any],
) -> DebounceCfg:
    """Convert legacy debouncing config to DebounceCfg.

    Args:
        config: Legacy config tuple or dict

    Returns:
        DebounceCfg instance
    """
    if isinstance(config, (tuple, list)) and len(config) >= 1:
        window = config[0]
        scope_str = config[1] if len(config) > 1 else None
        scope = coerce_scope(scope_str) if scope_str else None
        return DebounceCfg(window=window, scope=scope)
    elif isinstance(config, dict):
        window = config.get("delay", config.get("window", 2))
        scope_str = config.get("scope")
        scope = coerce_scope(scope_str) if scope_str else None
        method = config.get("method")
        bucket = config.get("bucket")
        return DebounceCfg(window=window, scope=scope, method=method, bucket=bucket)
    else:
        raise ValueError(f"Invalid legacy debouncing config: {config}")
