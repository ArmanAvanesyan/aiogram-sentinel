"""Bounded opaque component observations and fused host commit payloads."""

from __future__ import annotations

# This module owns its ephemeral domain Engine and never imports navigation.
# pyright: reportPrivateUsage=false
import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ..errors import BackendInconsistent, VersionConflict
from ..models import IdleConversationKey
from .canonical import CanonicalRows, body
from .canonical_scripts import META, ROWS
from .redis_transport import array, text
from .wire_json import compact, strict

if TYPE_CHECKING:
    from .redis_engine import Engine
    from .redis_store import RedisStore


def component_prefix(store: RedisStore, key: IdleConversationKey, component: str) -> str:
    if (
        not isinstance(cast(object, component), str)
        or not component
        or len(component) > 128
        or component == "__idle_owner__"
    ):
        from ..errors import ConfigurationError

        raise ConfigurationError("Canonical component name must be bounded")
    return (
        f"{store.prefix}:component:{store.ident(key)}:"
        + hashlib.sha256(component.encode()).hexdigest()
    )


def row_key(prefix: str, operation_id: str) -> str:
    return prefix + ":operation:" + hashlib.sha256(operation_id.encode()).hexdigest()


def keys(store: RedisStore, key: IdleConversationKey, component: str) -> list[str]:
    prefix = component_prefix(store, key, component)
    return [
        store.keys(key)[0],
        store.prefix + ":created",
        store.prefix + ":config",
        store.prefix + ":config-established",
        store.prefix + ":parked",
        prefix + ":metadata",
        prefix + ":expiry",
        prefix + ":indexes",
        prefix + ":protected",
        prefix + ":index-count",
    ]


def pairs(value: object) -> dict[str, str]:
    items = array(value)
    if len(items) % 2:
        raise BackendInconsistent("Malformed canonical observation")
    return {text(items[index]): text(items[index + 1]) for index in range(0, len(items), 2)}


@dataclass
class CanonicalObservation:
    payload: dict[str, object]
    metadata: dict[str, str]
    prefix: str


async def observe(
    store: RedisStore,
    engine: Engine,
    raw: str,
    config: str,
    component: str,
    *,
    operation_id: str = "",
    token: str = "",
    reservation_id: str = "",
    requested_ids: tuple[str, ...] = (),
    index_keys: tuple[str, ...] = (),
) -> CanonicalObservation:
    key = engine.key
    revision, hot, identity = body(engine._records.get(key), component)
    prefix = component_prefix(store, key, component)
    wirekeys = keys(store, key, component)
    response = array(
        await store.connection.script(
            META,
            wirekeys,
            [
                raw,
                store.history,
                config,
                store.member(key),
                hot or "",
                operation_id,
                token,
                reservation_id,
                prefix + ":operation:",
                compact(requested_ids),
                compact(index_keys),
            ],
            mutation=False,
        )
    )
    if text(response[0]) == "conflict":
        raise VersionConflict("Canonical observation changed")
    if len(response) != 8 or text(response[0]) != "ok":
        raise BackendInconsistent("Malformed canonical metadata response")
    metadata = pairs(response[4])
    expiry: dict[str, int] = {}
    for name, value in pairs(response[5]).items():
        try:
            number = float(value)
            if (
                not math.isfinite(number)
                or number < 0
                or number > 9_007_199_254_740_991
                or not number.is_integer()
            ):
                raise ValueError
            expiry[name] = int(number)
        except (ValueError, OverflowError) as error:
            raise BackendInconsistent("Malformed canonical expiry proof") from error
    descriptors: list[dict[str, str]] = []
    for name, encoded in metadata.items():
        value = strict(encoded)
        if (
            set(value) != {"key", "status", "index_fields"}
            or value["key"] != row_key(prefix, name)
            or value["status"] not in {"terminal", "protected"}
        ):
            raise BackendInconsistent("Canonical operation key proof changed")
        fields = value["index_fields"]
        if not isinstance(fields, list) or any(
            not isinstance(item, str) or not item or len(item) > 258
            for item in cast(list[object], fields)
        ):
            raise BackendInconsistent("Canonical reverse index proof changed")
        descriptors.append({"id": name, "metadata": encoded})
    rows_response = array(
        await store.connection.script(
            ROWS,
            [*wirekeys, *(row_key(prefix, item["id"]) for item in descriptors)],
            [raw, store.history, config, store.member(key), compact(descriptors)],
            mutation=False,
        )
    )
    if text(rows_response[0]) == "conflict":
        raise VersionConflict("Canonical rows changed during observation")
    if len(rows_response) != 4 or text(rows_response[0]) != "ok":
        raise BackendInconsistent("Malformed canonical row response")
    now = int(text(rows_response[2])) + int(text(rows_response[3])) / 1_000_000
    store.clock.update(now)
    rows = pairs(rows_response[1])
    for name, encoded in rows.items():
        value = strict(encoded)
        if value.get("id") != name or value.get("conversation") != identity:
            raise BackendInconsistent("Canonical operation identity changed")
    expired = [text(item) for item in array(response[6])]
    payload: dict[str, object] = {
        "revision": revision,
        "hot": hot,
        "operations": rows,
        "retained_count": int(cast(int, response[3])),
        "operation_expiry": expiry,
        "expired": expired,
        "indexes": {field: owner or None for field, owner in pairs(response[7]).items()},
    }
    return CanonicalObservation(payload, metadata, prefix)


def seed(engine: Engine, component: str, observation: CanonicalObservation) -> None:
    rows = cast(dict[str, str], observation.payload["operations"])
    expiry = cast(dict[str, int], observation.payload["operation_expiry"])
    indexes: dict[str, str] = {}
    for operation_id, encoded in observation.metadata.items():
        value = strict(encoded)
        for field in cast(list[str], value["index_fields"]):
            indexes[field] = operation_id
    engine._canonical_rows[(engine.key, component)] = CanonicalRows(
        dict(rows),
        dict(expiry),
        indexes,
        set(observation.metadata),
        int(cast(int, observation.payload["retained_count"])) - len(observation.metadata),
    )


def commit_payload(
    store: RedisStore,
    engine: Engine,
    component: str,
    delta: Mapping[str, object],
    *,
    cold_key_count: int,
) -> tuple[list[str], str]:
    from .canonical import delta_payload, names, strings

    _, _, identity = body(engine._records.get(engine.key), component)
    if identity is None:
        raise BackendInconsistent("Canonical component lost its identity")
    value = delta_payload(delta, identity=identity, max_bytes=store.config.max_components_bytes)
    context = cast(CanonicalObservation, engine.canonical_observation)
    ids = sorted(set(strings(value["put"])) | set(names(value["delete"])))
    if len(ids) > 64:
        from ..errors import Overloaded

        raise Overloaded(
            "Canonical mutation batch exceeds its bound", reason="batch", limit=64, used=len(ids)
        )
    rowkeys = {name: row_key(context.prefix, name) for name in ids}
    metadata: dict[str, str] = {}
    put = strings(value["put"])
    indexes = strings(value["token_index_put"], key_limit=258, value_limit=256)
    for name, raw in put.items():
        status = strict(raw)["status"]
        fields = {index for index, owner in indexes.items() if owner == name}
        previous = context.metadata.get(name)
        if previous:
            fields.update(cast(list[str], strict(previous)["index_fields"]))
        metadata[name] = compact(
            {
                "key": rowkeys[name],
                "status": "terminal" if status in {"completed", "failed"} else "protected",
                "index_fields": sorted(fields),
            }
        )
    basekeys = keys(store, engine.key, component)
    suffix = [
        *basekeys[5:9],
        store.prefix + ":component-sweep",
        basekeys[9],
        *(rowkeys[name] for name in ids),
    ]
    member = compact({"key": store.member(engine.key), "component": component})
    return suffix, compact(
        {
            "key_start": 12 + cold_key_count,
            "identity": identity,
            "delta": value,
            "row_keys": rowkeys,
            "metadata": metadata,
            "expected_rows": {
                name: cast(Mapping[str, str], context.payload["operations"]).get(name)
                for name in ids
            },
            "member": member,
        }
    )
