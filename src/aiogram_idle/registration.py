"""Small immutable registration values for ordinary application handlers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from .models import JsonObject, freeze_object, validate_identifier


@dataclass(frozen=True)
class ActivityRegistration:
    """Describe a flow without constructing a session or activity snapshot."""

    activity_key: str
    policy_id: str
    adapter_key: str
    params: Mapping[str, object] = field(default_factory=lambda: dict[str, object]())

    def __post_init__(self) -> None:
        for value in (self.activity_key, self.policy_id, self.adapter_key):
            validate_identifier(value, "activity registration identifier")
            if not isinstance(cast(object, value), str) or not value or len(value) > 128:
                raise ValueError("Registration identifiers must contain 1 to 128 characters")
        object.__setattr__(self, "params", freeze_object(self.params))

    @property
    def parameters(self) -> JsonObject:
        return freeze_object(self.params)
