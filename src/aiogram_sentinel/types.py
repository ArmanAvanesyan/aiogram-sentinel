"""Type definitions for aiogram-sentinel."""

from __future__ import annotations

from dataclasses import dataclass

from .storage.base import (
    DebounceBackend,
    RateLimiterBackend,
)


@dataclass
class InfraBundle:
    """Bundle of infrastructure backends managed by the library."""

    rate_limiter: RateLimiterBackend
    debounce: DebounceBackend

    def __post_init__(self) -> None:
        """Validate that all infrastructure backends are provided."""
        if not self.rate_limiter:
            raise ValueError("rate_limiter backend is required")
        if not self.debounce:
            raise ValueError("debounce backend is required")
