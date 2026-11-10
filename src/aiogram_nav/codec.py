"""Versioned, explicitly tagged JSON persistence without arbitrary constructors."""

from __future__ import annotations

import json
import math
import types
from collections.abc import Callable, Mapping
from dataclasses import fields
from typing import Any, Literal, Union, cast, get_args, get_origin, get_type_hints

from . import models
from .errors import ConfigurationError, SchemaUnsupported
from .json import freeze_json, freeze_object

_CLASSES: tuple[type[Any], ...] = (
    models.ConversationKey,
    models.MessageRef,
    models.RenderResult,
    models.ViewState,
    models.HistoryEntry,
    models.NavigationSnapshot,
    models.VersionedSnapshot,
    models.NavigationAction,
    models.NavigationIntent,
    models.EffectCheckpoint,
    models.PreparedAction,
    models.NavigationMutation,
    models.CommitResult,
    models.ActionStatus,
    models.NavigationToken,
    models.NavigationEvent,
)
_NAMES = {cls.__name__: cls for cls in _CLASSES}


def _bad() -> ConfigurationError:
    return ConfigurationError("Malformed navigation persistence record")


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise _bad()
        result[key] = value
    return result


def encode(value: object, *, max_bytes: int = 8_388_608, schema_version: int = 1) -> str:
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise SchemaUnsupported("Unsupported navigation persistence schema")
    result = json.dumps(
        {"schema_version": schema_version, "value": encode_value(value)},
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    if len(result.encode()) > max_bytes:
        raise _bad()
    return result


def decode(value: str, *, max_bytes: int = 8_388_608) -> object:
    if not isinstance(cast(object, value), str) or len(value.encode()) > max_bytes:
        raise _bad()
    try:
        root = _mapping(json.loads(value, object_pairs_hook=_pairs))
        if set(root) != {"schema_version", "value"}:
            raise _bad()
        if type(root["schema_version"]) is not int or root["schema_version"] not in (1, 2):
            raise SchemaUnsupported("Unsupported navigation persistence schema")
        return decode_value(root["value"])
    except SchemaUnsupported:
        raise
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise _bad() from exc


def encode_value(value: object, *, _depth: int = 0) -> object:
    if _depth > 64:
        raise _bad()
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _bad()
        return value
    if type(value) in _CLASSES:
        cls = type(value)
        obj = cast(Any, value)
        data = {field.name: getattr(obj, field.name) for field in fields(obj)}
        _construct(cls, data)
        return {
            "type": cls.__name__,
            "value": {name: encode_value(child, _depth=_depth + 1) for name, child in data.items()},
        }
    if isinstance(value, Mapping):
        data = cast(Mapping[object, object], value)
        if not all(isinstance(key, str) for key in data):
            raise _bad()
        return {
            "type": "mapping",
            "value": {
                cast(str, key): encode_value(child, _depth=_depth + 1)
                for key, child in data.items()
            },
        }
    if isinstance(value, (tuple, list)):
        return {
            "type": "tuple" if isinstance(value, tuple) else "list",
            "value": [
                encode_value(child, _depth=_depth + 1) for child in cast(tuple[object, ...], value)
            ],
        }
    raise _bad()


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _bad()
    data = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in data):
        raise _bad()
    return {cast(str, key): child for key, child in data.items()}


def decode_value(value: object, *, _depth: int = 0) -> object:
    if _depth > 64:
        raise _bad()
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _bad()
        return value
    data = _mapping(value)
    if set(data) != {"type", "value"} or not isinstance(data["type"], str):
        raise _bad()
    tag, body = data["type"], data["value"]
    if tag in {"tuple", "list"}:
        if not isinstance(body, list):
            raise _bad()
        values = [decode_value(child, _depth=_depth + 1) for child in cast(list[object], body)]
        return tuple(values) if tag == "tuple" else values
    if tag == "mapping":
        return {
            name: decode_value(child, _depth=_depth + 1) for name, child in _mapping(body).items()
        }
    cls = _NAMES.get(tag)
    if cls is None:
        raise SchemaUnsupported("Unsupported navigation record type")
    return _construct(
        cls,
        {name: decode_value(child, _depth=_depth + 1) for name, child in _mapping(body).items()},
    )


def _matches(value: object, hint: object) -> bool:
    origin, args = get_origin(hint), get_args(hint)
    if hint is Any:
        return True
    if hint is type(None):
        return value is None
    if origin in (Union, types.UnionType):
        return any(_matches(value, child) for child in args)
    if origin is Literal:
        return any(type(value) is type(child) and value == child for child in args)
    if origin is tuple:
        if not isinstance(value, tuple):
            return False
        items = cast(tuple[object, ...], value)
        return (
            all(_matches(child, args[0]) for child in items)
            if len(args) == 2 and args[1] is Ellipsis
            else (
                len(items) == len(args)
                and all(_matches(child, kind) for child, kind in zip(items, args, strict=True))
            )
        )
    if origin is Mapping:
        return isinstance(value, Mapping) and all(
            _matches(key, args[0]) and _matches(child, args[1])
            for key, child in cast(Mapping[object, object], value).items()
        )
    if hint is str or hint is int or hint is bool or hint is float:
        return type(value) is hint
    return isinstance(value, hint) if isinstance(hint, type) else False


def _construct(cls: type[Any], data: dict[str, object]) -> object:
    if set(data) != {field.name for field in fields(cls)}:
        raise _bad()
    if cls is models.NavigationSnapshot and data["schema_version"] != 1:
        raise SchemaUnsupported("Unsupported navigation snapshot schema")
    hints = get_type_hints(cls)
    for name, value in data.items():
        if name == "params":
            freeze_object(value)
        elif cls is models.EffectCheckpoint and name == "result":
            if not isinstance(value, models.RenderResult):
                freeze_json(value)
        elif not _matches(value, hints[name]):
            raise _bad()
    try:
        return cast(Callable[..., object], cls)(**data)
    except (ValueError, TypeError, OverflowError) as exc:
        raise _bad() from exc


def dumps_snapshot(snapshot: models.NavigationSnapshot) -> str:
    return encode(snapshot)


def loads_snapshot(value: str) -> models.NavigationSnapshot:
    result = decode(value)
    if not isinstance(result, models.NavigationSnapshot):
        raise _bad()
    return result
