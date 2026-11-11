"""Explicit policy inheritance and activity grouping for navigation nodes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from aiogram_nav.registry import NavigationRegistry

from ...errors import ConfigurationError
from ...models import fingerprint
from ...policies import IdlePolicies


@dataclass(frozen=True, init=False)
class NodePolicies:
    default: str
    overrides: Mapping[str, str]
    activities: Mapping[str, str]

    def __init__(
        self,
        *,
        default: str,
        overrides: Mapping[str, str] | None = None,
        activities: Mapping[str, str] | None = None,
    ) -> None:
        if not isinstance(cast(object, default), str) or not default or len(default) > 128:
            raise ConfigurationError("A default idle policy is required")
        object.__setattr__(self, "default", default)
        try:
            overrides_copy, activities_copy = dict(overrides or {}), dict(activities or {})
        except (TypeError, ValueError) as error:
            raise ConfigurationError("Navigation policy mappings must be mappings") from error
        for mapping, limit in ((overrides_copy, 128), (activities_copy, 256)):
            if any(
                not isinstance(cast(object, key), str)
                or not key
                or len(key) > 256
                or not isinstance(cast(object, value), str)
                or not value
                or len(value) > limit
                for key, value in mapping.items()
            ):
                raise ConfigurationError("Invalid navigation policy/activity mapping")
        object.__setattr__(self, "overrides", MappingProxyType(overrides_copy))
        object.__setattr__(self, "activities", MappingProxyType(activities_copy))

    def validate(self, registry: NavigationRegistry, policies: IdlePolicies) -> None:
        policies[self.default]
        for node, policy in self.overrides.items():
            registry.get(node)
            policies[policy]
        for node in self.activities:
            registry.get(node)

    def policy_for(self, registry: NavigationRegistry, node_id: str) -> str:
        for node in registry.ancestors(node_id):
            if node.id in self.overrides:
                return self.overrides[node.id]
        return self.default

    def activity_for(self, node_id: str) -> str:
        # Grouping is exact and explicit, never inferred from dotted prefixes.
        return self.activities.get(node_id, node_id)

    @property
    def digest(self) -> str:
        return fingerprint(
            dict(default=self.default, overrides=self.overrides, activities=self.activities)
        )
