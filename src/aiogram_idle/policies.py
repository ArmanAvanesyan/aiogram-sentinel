"""Explicit idle policies; structural inheritance belongs to optional adapters."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import ClassVar, Literal, TypeAlias, cast

from .errors import ConfigurationError
from .models import validate_identifier

Controls: TypeAlias = Literal["reply", "inline", "commands", "hybrid"]


def _positive(value: float, name: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"{name} must be positive and finite")


@dataclass(frozen=True)
class ExemptPolicy:
    kind: ClassVar[str] = "exempt"


@dataclass(frozen=True)
class PromptPolicy:
    after_seconds: float = 600
    grace_seconds: float = 600
    controls: Controls = "inline"
    kind: ClassVar[str] = "prompt"

    def __post_init__(self) -> None:
        _positive(self.after_seconds, "after_seconds")
        _positive(self.grace_seconds, "grace_seconds")
        if self.controls not in {"reply", "inline", "commands", "hybrid"}:
            raise ConfigurationError("unknown prompt controls")


@dataclass(frozen=True)
class QuietRestorePolicy:
    after_seconds: float = 600
    kind: ClassVar[str] = "quiet_restore"

    def __post_init__(self) -> None:
        _positive(self.after_seconds, "after_seconds")


IdlePolicy: TypeAlias = ExemptPolicy | PromptPolicy | QuietRestorePolicy


def policy_digest(policy: IdlePolicy) -> str:
    value = {"kind": policy.kind, **asdict(policy)}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class IdlePolicies(Mapping[str, IdlePolicy]):
    def __init__(self, policies: Mapping[str, IdlePolicy]) -> None:
        if not policies:
            raise ConfigurationError("at least one idle policy is required")
        for key, policy in policies.items():
            validate_identifier(key, "policy_id")
            if not isinstance(cast(object, key), str) or not key or len(key) > 128:
                raise ConfigurationError("policy IDs must contain 1 to 128 characters")
            if not isinstance(
                cast(object, policy), (ExemptPolicy, PromptPolicy, QuietRestorePolicy)
            ):
                raise ConfigurationError("unsupported idle policy")
        self._policies = MappingProxyType(dict(policies))

    def __getitem__(self, key: str) -> IdlePolicy:
        try:
            return self._policies[key]
        except KeyError as exc:
            raise ConfigurationError("unknown idle policy") from exc

    def __iter__(self) -> Iterator[str]:
        return iter(self._policies)

    def __len__(self) -> int:
        return len(self._policies)

    @property
    def digest(self) -> str:
        pairs = {name: policy_digest(policy) for name, policy in self.items()}
        return hashlib.sha256(json.dumps(pairs, sort_keys=True).encode()).hexdigest()
