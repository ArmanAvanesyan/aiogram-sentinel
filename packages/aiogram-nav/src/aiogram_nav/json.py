"""Finite JSON values, defensive freezing and canonical operation fingerprints."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import TypeAlias, cast

from .errors import InvalidParameters

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
JsonObject: TypeAlias = Mapping[str, JsonValue]


def freeze_json(value: object, *, _depth: int = 0) -> JsonValue:
    if _depth > 32:
        raise InvalidParameters("JSON nesting exceeds the supported depth")
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeError as error:
            raise InvalidParameters("JSON strings must contain valid Unicode scalars") from error
        return value
    if value is None or type(value) in (bool, int):
        return cast(JsonScalar, value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidParameters("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        if not all(isinstance(key, str) for key in mapping):
            raise InvalidParameters("JSON object keys must be strings")
        try:
            for key in mapping:
                cast(str, key).encode("utf-8")
        except UnicodeError as error:
            raise InvalidParameters(
                "JSON object keys must contain valid Unicode scalars"
            ) from error
        return MappingProxyType(
            {
                cast(str, key): freeze_json(child, _depth=_depth + 1)
                for key, child in mapping.items()
            }
        )
    if isinstance(value, (tuple, list)):
        return tuple(
            freeze_json(child, _depth=_depth + 1) for child in cast(tuple[object, ...], value)
        )
    raise InvalidParameters("Only JSON-compatible parameter values are supported")


def thaw_json(value: JsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(child) for child in value]
    return value


def freeze_object(value: object, *, max_bytes: int = 16_384) -> JsonObject:
    if not isinstance(value, Mapping):
        raise InvalidParameters("Parameters must be a JSON object")
    frozen = cast(JsonObject, freeze_json(cast(object, value)))
    try:
        size = len(json.dumps(thaw_json(frozen), ensure_ascii=False, allow_nan=False).encode())
    except (ValueError, TypeError, OverflowError) as exc:
        raise InvalidParameters("JSON object cannot be represented safely") from exc
    if size > max_bytes:
        raise InvalidParameters("JSON object exceeds its configured size limit")
    return frozen


def empty_object() -> JsonObject:
    return MappingProxyType({})


def fingerprint(value: JsonValue) -> str:
    data = json.dumps(
        thaw_json(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(data.encode()).hexdigest()


def timestamp_ms(value: datetime | int) -> int:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Expiry must be timezone-aware")
        return int(value.timestamp() * 1000)
    if type(value) is not int:
        raise ValueError("Timestamps must be integer epoch milliseconds")
    return value


def identifier(value: object, name: str = "identifier") -> None:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"{name} must contain 1 to 256 characters")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"{name} must contain valid Unicode scalars") from error
