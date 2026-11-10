"""Versioned, whitelist-only JSON persistence. Never imports Redis or navigation."""

from __future__ import annotations

import json
import math
import types
from collections.abc import Callable, Mapping
from dataclasses import fields
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from .. import models
from ..errors import BackendInconsistent, Overloaded, SchemaUnsupported
from ..models import freeze_object
from ..policies import ExemptPolicy, PromptPolicy, QuietRestorePolicy
from ..presentation import DeliveryReceipt, PromptReceipt
from .state import Claim, ControlToken, Job, OperationReceipt

_CLASSES: tuple[type[Any], ...] = (
    models.IdleConversationKey,
    models.SessionGuard,
    models.SessionSnapshot,
    models.ActivityGuard,
    models.ActivitySnapshot,
    models.MessageRef,
    models.PendingOperation,
    models.IdleSnapshot,
    models.RuntimeSnapshot,
    models.ActivitySpec,
    models.ActionReceipt,
    models.ConfigManifest,
    PromptReceipt,
    DeliveryReceipt,
    ExemptPolicy,
    PromptPolicy,
    QuietRestorePolicy,
    Claim,
    ControlToken,
    Job,
    OperationReceipt,
)
_REGISTRY = {cls.__name__: cls for cls in _CLASSES}
_JSON_FIELDS = {"params", "effects", "details", "components", "component_updates"}
_MAX_DEPTH = 64
_MAX_BYTES = 32 * 1024 * 1024


def _bad() -> BackendInconsistent:
    return BackendInconsistent("malformed persisted idle record")


def encode(value: object, *, schema_version: int = 1) -> str:
    """Encode a supported record or string-keyed envelope, without lossy coercion."""
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise SchemaUnsupported("unsupported persistence schema")
    body = json.dumps(
        {"schema_version": schema_version, "value": encode_value(value)},
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(body.encode()) > _MAX_BYTES:
        raise Overloaded(
            "Idle persistence envelope exceeds supported limits",
            reason="bytes",
            size_bytes=len(body.encode()),
        )
    return body


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise _bad()
        result[key] = value
    return result


def decode(text: str) -> object:
    """Decode supported schema 1 or 2; corruption fails closed, without dynamic imports."""
    if not isinstance(cast(object, text), str) or len(text.encode()) > _MAX_BYTES:
        raise _bad()
    try:
        raw: object = json.loads(text, object_pairs_hook=_pairs)
        root = _mapping(raw)
        if set(root) != {"schema_version", "value"}:
            raise _bad()
        version = root["schema_version"]
        if type(version) is not int or version not in (1, 2):
            raise SchemaUnsupported("unsupported persistence schema")
        return decode_value(root["value"])
    except SchemaUnsupported:
        raise
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise _bad() from exc


def encode_value(value: object, *, _depth: int = 0) -> object:
    """Encode a nested value. Every container is tagged to prevent tag collisions."""
    if _depth > _MAX_DEPTH:
        raise _bad()
    if isinstance(value, models.Phase):
        return {"type": "Phase", "value": value.value}
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _bad()
        return value
    if type(value) in _CLASSES:
        cls = type(value)
        obj = cast(Any, value)
        payload = {
            field.name: encode_value(getattr(obj, field.name), _depth=_depth + 1)
            for field in fields(obj)
        }
        # Apply the same strict validation to writes and reads.
        _construct(cls, {field.name: getattr(obj, field.name) for field in fields(obj)})
        return {"type": cls.__name__, "value": payload}
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        if not all(isinstance(key, str) for key in mapping):
            raise _bad()
        return {
            "type": "mapping",
            "value": {
                cast(str, key): encode_value(child, _depth=_depth + 1)
                for key, child in mapping.items()
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
    mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        raise _bad()
    return {cast(str, key): child for key, child in mapping.items()}


def decode_value(value: object, *, _depth: int = 0) -> object:
    """Decode one tagged nested value, validating all fields before construction."""
    if _depth > _MAX_DEPTH:
        raise _bad()
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _bad()
        return value
    node = _mapping(value)
    if set(node) != {"type", "value"} or not isinstance(node["type"], str):
        raise _bad()
    tag, payload = node["type"], node["value"]
    if tag == "Phase":
        if not isinstance(payload, str):
            raise _bad()
        try:
            return models.Phase(payload)
        except ValueError as exc:
            raise _bad() from exc
    if tag in {"list", "tuple"}:
        if not isinstance(payload, list):
            raise _bad()
        result = [decode_value(child, _depth=_depth + 1) for child in cast(list[object], payload)]
        return tuple(result) if tag == "tuple" else result
    data = _mapping(payload)
    decoded = {key: decode_value(child, _depth=_depth + 1) for key, child in data.items()}
    if tag == "mapping":
        return decoded
    cls = _REGISTRY.get(tag)
    if cls is None:
        raise SchemaUnsupported("unsupported persisted record type")
    return _construct(cls, decoded)


def _matches(value: object, hint: object) -> bool:
    origin, args = get_origin(hint), get_args(hint)
    if origin in (types.UnionType, Union):
        return any(_matches(value, arg) for arg in args)
    if hint is type(None):
        return value is None
    if hint is float:
        return type(value) in (int, float) and math.isfinite(cast(float, value))
    if hint is int or hint is bool or hint is str:
        return type(value) is hint
    if origin is tuple:
        return isinstance(value, tuple) and all(
            _matches(child, args[0]) for child in cast(tuple[object, ...], value)
        )
    if origin is not None and str(origin) == "typing.Literal":
        return value in args
    if isinstance(hint, type):
        return isinstance(value, hint)
    return False


def _construct(cls: type[Any], data: dict[str, object]) -> object:
    if cls is models.ActionReceipt:
        data.setdefault("component_updates", {})
    if set(data) != {field.name for field in fields(cls)}:
        raise _bad()
    if cls is OperationReceipt:
        if (
            not isinstance(data["fingerprint"], str)
            or not data["fingerprint"]
            or not _matches(data["expires_at"], float)
            or type(data["result"])
            not in (
                models.SessionSnapshot,
                models.ActivitySnapshot,
                models.RuntimeSnapshot,
                models.ConfigManifest,
                bool,
            )
        ):
            raise _bad()
    else:
        hints = get_type_hints(cls, localns={"PromptReceipt": PromptReceipt})
        for name, value in data.items():
            if name in _JSON_FIELDS:
                try:
                    freeze_object(
                        value,
                        max_bytes=8_388_608
                        if name in {"components", "component_updates", "effects"}
                        else 16_384,
                    )
                except (ValueError, TypeError, OverflowError) as exc:
                    raise _bad() from exc
            elif not _matches(value, hints[name]):
                raise _bad()
    _validate(data, cls)
    try:
        result = cast(Callable[..., object], cls)(**data)
        if isinstance(result, models.RuntimeSnapshot):
            from .component_transaction import ownership

            ownership(result)
        return result
    except (ValueError, TypeError, OverflowError) as exc:
        raise _bad() from exc


def _validate(data: dict[str, object], cls: type[Any]) -> None:
    if cls is models.PendingOperation and data["kind"] not in {
        "prompt",
        "continue",
        "cancel",
        "timed_out",
        "restored",
    }:
        raise SchemaUnsupported("Unsupported idle operation kind")
    for name, value in data.items():
        if name in {"attempts"} and (type(value) is not int or value < 0):
            raise _bad()
        if name in {"store_version", "generation", "message_id", "chat_id"} and isinstance(
            value, int
        ):
            if isinstance(value, bool) or value < 1:
                raise _bad()
        if name.endswith("_id") or name in {"token", "fingerprint", "kind", "stage", "generation"}:
            if isinstance(value, str) and (len(value) > 256 or not value):
                if not (name == "operation_id" and cls is models.ActionReceipt):
                    raise _bad()
    if cls is models.ConfigManifest and (not data["generation"] or not data["policies_digest"]):
        raise _bad()
    if cls is PromptReceipt and data["controls"] not in {"reply", "inline", "commands", "hybrid"}:
        raise _bad()
    if cls is models.RuntimeSnapshot:
        session = cast(models.SessionSnapshot, data["session"])
        activity = data["activity"]
        if (
            isinstance(activity, models.ActivitySnapshot)
            and activity.session_id != session.session_id
        ):
            raise _bad()


def dumps_snapshot(snapshot: models.RuntimeSnapshot) -> str:
    return encode(snapshot)


def loads_snapshot(text: str) -> models.RuntimeSnapshot:
    value = decode(text)
    if not isinstance(value, models.RuntimeSnapshot):
        raise _bad()
    return value
