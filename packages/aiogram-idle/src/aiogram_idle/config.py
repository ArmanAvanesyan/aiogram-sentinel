"""Validated library settings; importing the package never reads the environment."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from enum import Enum
from typing import Literal, cast

from .errors import ConfigurationError


class AmbiguousSendPolicy(str, Enum):
    SUPPRESS = "suppress"
    RETRY = "retry"


@dataclass(frozen=True)
class IdleConfig:
    engine: Literal["python", "rust"] = "python"
    enabled: bool = False
    poll_seconds: float = 10
    concurrency: int = 8
    claim_limit: int = 8
    lease_seconds: float = 60
    renew_seconds: float = 15
    operation_timeout_seconds: float = 45
    lock_wait_seconds: float = 5
    shutdown_seconds: float = 10
    retry_max_attempts: int = 5
    retry_max_age_seconds: float = 300
    recovery_retention_seconds: float = 3600
    replay_retention_seconds: float | None = None
    ambiguous_send: AmbiguousSendPolicy = AmbiguousSendPolicy.SUPPRESS
    max_conversations: int = 10_000
    max_receipts_per_conversation: int = 256
    max_tokens_per_conversation: int = 16
    max_params_bytes: int = 16_384
    max_components_bytes: int = 8_388_608

    def __post_init__(self) -> None:
        if self.engine not in ("python", "rust"):
            raise ConfigurationError("engine must be python or rust")
        if not isinstance(cast(object, self.enabled), bool):
            raise ConfigurationError("enabled must be a boolean")
        integer_fields = {
            "concurrency",
            "claim_limit",
            "retry_max_attempts",
            "max_conversations",
            "max_receipts_per_conversation",
            "max_tokens_per_conversation",
            "max_params_bytes",
            "max_components_bytes",
        }
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name in {"engine", "enabled", "ambiguous_send"} or (
                field.name == "replay_retention_seconds" and value is None
            ):
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ConfigurationError(f"{field.name} must be numeric")
            if not math.isfinite(value) or value <= 0:
                raise ConfigurationError(f"{field.name} must be positive and finite")
            if field.name in integer_fields and not isinstance(value, int):
                raise ConfigurationError(f"{field.name} must be an integer")
        if self.max_components_bytes > 8_388_608:
            raise ConfigurationError("max_components_bytes exceeds the supported 8 MiB bound")
        if self.claim_limit > self.concurrency:
            raise ConfigurationError("claim_limit exceeds worker concurrency")
        if self.renew_seconds * 2 >= self.lease_seconds:
            raise ConfigurationError("renew interval must be below half the lease")
        if self.lock_wait_seconds >= self.lease_seconds:
            raise ConfigurationError("lock wait must be shorter than lease")
        if not isinstance(cast(object, self.ambiguous_send), AmbiguousSendPolicy):
            raise ConfigurationError("unknown ambiguous-send policy")

    @property
    def effective_replay_retention_seconds(self) -> float:
        return (
            self.recovery_retention_seconds
            if self.replay_retention_seconds is None
            else self.replay_retention_seconds
        )


STORAGE_CONFIG_FIELDS = (
    "recovery_retention_seconds",
    "replay_retention_seconds",
    "max_conversations",
    "max_receipts_per_conversation",
    "max_tokens_per_conversation",
    "max_params_bytes",
    "max_components_bytes",
)
