"""Type definitions for aiogram-sentinel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .storage.base import BlocklistBackend, DebounceBackend, RateLimiterBackend, UserRepo


@dataclass
class BackendsBundle:
    """Bundle of storage backends for aiogram-sentinel."""
    
    rate_limiter: RateLimiterBackend
    debounce: DebounceBackend
    blocklist: BlocklistBackend
    user_repo: UserRepo
    
    def __post_init__(self) -> None:
        """Validate that all backends are provided."""
        if not self.rate_limiter:
            raise ValueError("rate_limiter backend is required")
        if not self.debounce:
            raise ValueError("debounce backend is required")
        if not self.blocklist:
            raise ValueError("blocklist backend is required")
        if not self.user_repo:
            raise ValueError("user_repo backend is required")
