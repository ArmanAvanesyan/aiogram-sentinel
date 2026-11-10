"""Explicit validated settings; importing navigation reads no environment."""

import math
from dataclasses import dataclass
from typing import cast

from .errors import ConfigurationError


@dataclass(frozen=True)
class NavigationConfig:
    root: str | None = None
    session_seconds: float = 3600
    history_limit: int = 20
    recovery_seconds: float = 3600
    max_conversations: int = 10_000
    max_receipts: int = 256
    max_tokens: int = 128
    max_params_bytes: int = 16_384

    def __post_init__(self) -> None:
        if self.root is not None and (
            not isinstance(cast(object, self.root), str) or not self.root
        ):
            raise ConfigurationError("root must be a nonempty node ID")
        for value in (self.session_seconds, self.recovery_seconds):
            try:
                valid = (
                    not isinstance(value, bool)
                    and isinstance(cast(object, value), (int, float))
                    and math.isfinite(value)
                    and value > 0
                    and math.isfinite(value * 1000)
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ConfigurationError("Intervals must be positive and finite in milliseconds")
        for name in (
            "history_limit",
            "max_conversations",
            "max_receipts",
            "max_tokens",
            "max_params_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "history_limit" else 1):
                raise ConfigurationError(f"{name} must be a valid integer capacity")
            if name == "history_limit" and value > 1000:
                raise ConfigurationError("history_limit exceeds the supported bound")
