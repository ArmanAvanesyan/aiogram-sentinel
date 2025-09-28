"""Configuration for aiogram-sentinel."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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

    # Blocking configuration
    auto_block_on_limit: bool = True

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

        if not self.redis_prefix.endswith(":"):
            self.redis_prefix += ":"

    def is_redis_backend(self) -> bool:
        """Check if Redis backend is configured."""
        return self.backend == "redis"

    def is_memory_backend(self) -> bool:
        """Check if memory backend is configured."""
        return self.backend == "memory"
