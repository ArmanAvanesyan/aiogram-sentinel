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
    redis_prefix: str = "aiogram_sentinel:"
    
    # Rate limiting defaults
    default_rate_limit: int = 10
    default_rate_window: int = 60
    
    # Debouncing defaults
    default_debounce_delay: float = 1.0
    
    # Throttling defaults
    default_throttle_delay: float = 0.5
    
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
        
        if self.default_rate_limit <= 0:
            raise ConfigurationError("default_rate_limit must be positive")
        
        if self.default_rate_window <= 0:
            raise ConfigurationError("default_rate_window must be positive")
        
        if self.default_debounce_delay < 0:
            raise ConfigurationError("default_debounce_delay must be non-negative")
        
        if self.default_throttle_delay < 0:
            raise ConfigurationError("default_throttle_delay must be non-negative")
        
        if not self.redis_prefix.endswith(":"):
            self.redis_prefix += ":"

    def is_redis_backend(self) -> bool:
        """Check if Redis backend is configured."""
        return self.backend == "redis"

    def is_memory_backend(self) -> bool:
        """Check if memory backend is configured."""
        return self.backend == "memory"
