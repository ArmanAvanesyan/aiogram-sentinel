"""Versioned opaque navigation ledger carried in an idle-owned component."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict

from aiogram_nav.config import NavigationConfig
from aiogram_nav.models import ConversationKey
from aiogram_nav.registry import NavigationRegistry
from aiogram_nav.storage.redis_codec import dumps, loads
from aiogram_nav.storage.state import Conversation

from ...errors import ConfigurationError, SchemaUnsupported
from ...models import JsonObject, RuntimeSnapshot, fingerprint, freeze_object
from .policies import NodePolicies

COMPONENT = "aiogram_nav"
OWNER = "__idle_owner__"


def profile(config: NavigationConfig, policies: NodePolicies, registry: NavigationRegistry) -> str:
    tree = [
        dict(
            id=node.id,
            parent=node.parent,
            back_to=node.back_to,
            cancel_to=node.cancel_to,
            renderer=node.renderer,
            metadata=node.metadata,
        )
        for node in sorted(registry.nodes.values(), key=lambda item: item.id)
    ]
    config_values = asdict(config)
    config_values.pop("engine", None)
    if config_values.get("replay_retention_seconds") is None:
        config_values.pop("replay_retention_seconds", None)
    return fingerprint(
        {
            "adapter_format": 1,
            "stage_format": 1,
            "config": config_values,
            "policies": policies.digest,
            "registry": tree,
            "roots": sorted(registry.roots),
            "migrations": registry.migrations,
            "safe_root": registry.safe_root,
        }
    )


def component(record: RuntimeSnapshot | None, *, expected_profile: str) -> JsonObject | None:
    if record is None or COMPONENT not in record.components:
        return None
    value = record.components[COMPONENT]
    if (
        not isinstance(value, Mapping)
        or type(value.get("schema")) is not int
        or value.get("schema") not in (1, 3)
    ):
        raise SchemaUnsupported("Unsupported integrated navigation component")
    if value.get("profile") != expected_profile:
        raise ConfigurationError("Integrated navigation configuration changed without migration")
    if value.get("schema") == 3:
        from ...storage.canonical import body

        body(record, COMPONENT)
        return value
    if not isinstance(value.get("ledger"), str):
        raise SchemaUnsupported("Malformed integrated navigation ledger")
    return value


def load_ledger(
    record: RuntimeSnapshot | None, key: ConversationKey, *, expected_profile: str
) -> Conversation | None:
    value = component(record, expected_profile=expected_profile)
    if value is None:
        return None
    if value.get("schema") == 3:
        if value.get("hot") is None:
            return None
        hot = json.loads(str(value["hot"]))
        core = hot["core"]
        fields = core["value"]["value"]
        # A synchronous presentation-only view never reconstructs historical rows.
        # Recovery and mutations use the asynchronous canonical ledger reader.
        fields["pending_id"] = None
        fields["tokens"] = {"type": "mapping", "value": {}}
        return loads(json.dumps(core), key)
    return loads(str(value["ledger"]), key)


def save_component(
    ledger: Conversation, key: ConversationKey, *, expected_profile: str
) -> JsonObject:
    return freeze_object(
        {
            "schema": 1,
            "profile": expected_profile,
            "ledger": dumps(
                key, ledger, storage_format=2 if ledger.external_session is not None else 1
            ),
        },
        max_bytes=8_388_608,
    )
