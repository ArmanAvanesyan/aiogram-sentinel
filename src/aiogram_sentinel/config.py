"""Configuration for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, cast

from .actions import ActionKind, ActionPolicy, SentinelExemptions
from .exceptions import ConfigurationError


@dataclass
class SentinelConfig:
    """Configuration for aiogram-sentinel."""

    # Backend selection
    backend: Literal["memory", "redis"] = "memory"

    # Redis configuration (used when backend="redis")
    redis_url: str = "redis://localhost:6379"
    redis_prefix: str = "sentinel"

    # Rate limiting defaults
    throttling_default_max: int = 5
    throttling_default_per_seconds: int = 10

    # Debouncing defaults
    debounce_default_window: int = 2

    # Auth configuration
    require_registration: bool = False

    # Explicit opt-ins: existing shared/default behavior stays unchanged.
    action_policies: Mapping[ActionKind, ActionPolicy] = field(
        default_factory=lambda: dict[ActionKind, ActionPolicy]()
    )
    bucket_mode: Literal["shared", "action_kind"] = "shared"
    exemptions: SentinelExemptions = field(default_factory=SentinelExemptions)

    # Internal settings
    _validated: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self._validate()
        self._validated = True

    def _validate(self) -> None:
        """Validate configuration values."""
        if self.backend not in ("memory", "redis"):
            raise ConfigurationError(f"Invalid backend: {self.backend}")

        if self.backend == "redis" and not self.redis_url:
            raise ConfigurationError("redis_url is required when backend='redis'")

        if self.throttling_default_max <= 0:
            raise ConfigurationError("throttling_default_max must be positive")

        if self.throttling_default_per_seconds <= 0:
            raise ConfigurationError("throttling_default_per_seconds must be positive")

        if self.debounce_default_window <= 0:
            raise ConfigurationError("debounce_default_window must be positive")

        if self.bucket_mode not in ("shared", "action_kind"):
            raise ConfigurationError("bucket_mode must be shared or action_kind")
        if not isinstance(cast(object, self.exemptions), SentinelExemptions):
            raise ConfigurationError("exemptions must be SentinelExemptions")
        if not isinstance(cast(object, self.action_policies), Mapping):
            raise ConfigurationError("action_policies must be a mapping")
        if any(
            kind not in ("message", "command", "callback_query")
            or not isinstance(cast(object, policy), ActionPolicy)
            for kind, policy in self.action_policies.items()
        ):
            raise ConfigurationError("Invalid action policy mapping")
        self.action_policies = MappingProxyType(dict(self.action_policies))

    def is_redis_backend(self) -> bool:
        """Check if Redis backend is configured."""
        return self.backend == "redis"

    def is_memory_backend(self) -> bool:
        """Check if memory backend is configured."""
        return self.backend == "memory"
