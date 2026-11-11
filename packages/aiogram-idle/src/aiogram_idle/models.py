"""Immutable, navigation-independent public records and validated JSON values."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, TypeAlias, cast

from .errors import ConfigurationError, UnsupportedContext

if TYPE_CHECKING:
    from aiogram import Bot

    from .presentation import PromptReceipt
    from .protocols import EffectRecorder

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
JsonObject: TypeAlias = Mapping[str, JsonValue]


def validate_unicode(value: str, name: str = "JSON string") -> None:
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise ConfigurationError(f"{name} must contain valid UTF-8 Unicode scalars") from error


_utf8 = validate_unicode


def validate_identifier(value: str, name: str) -> None:
    if not isinstance(cast(object, value), str) or not value or len(value) > 256:
        raise ConfigurationError(f"{name} must contain 1 to 256 characters")
    _utf8(value, name)


_identifier = validate_identifier


def _revision(value: int) -> None:
    if isinstance(value, bool) or not isinstance(cast(object, value), int) or value < 1:
        raise ConfigurationError("revision must be a positive integer")


def freeze_json(value: object, *, max_bytes: int = 16_384) -> JsonValue:
    """Validate finite bounded JSON and detach nested mutable caller structures."""

    def freeze(item: object, depth: int) -> JsonValue:
        if depth > 32:
            raise ConfigurationError("JSON nesting exceeds limit")
        if isinstance(item, str):
            _utf8(item)
            return item
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ConfigurationError("JSON numbers must be finite")
            return item
        if isinstance(item, Mapping):
            result: dict[str, JsonValue] = {}
            for key, child in cast(Mapping[object, object], item).items():
                if not isinstance(key, str):
                    raise ConfigurationError("JSON keys must be strings")
                _utf8(key, "JSON key")
                result[key] = freeze(child, depth + 1)
            return MappingProxyType(result)
        if isinstance(item, (list, tuple)):
            return tuple(freeze(child, depth + 1) for child in cast(tuple[object, ...], item))
        raise ConfigurationError("value is not JSON-compatible")

    result = freeze(value, 0)
    if len(json.dumps(thaw_json(result), allow_nan=False).encode()) > max_bytes:
        raise ConfigurationError("JSON value exceeds size limit")
    return result


def freeze_object(value: object, *, max_bytes: int = 16_384) -> JsonObject:
    result = freeze_json(value, max_bytes=max_bytes)
    if not isinstance(result, Mapping):
        raise ConfigurationError("expected a JSON object")
    return result


def thaw_json(value: JsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(child) for child in value]
    return value


def empty_object() -> JsonObject:
    return MappingProxyType({})


def fingerprint(value: object) -> str:
    frozen = freeze_json(value, max_bytes=1_048_576)
    encoded = json.dumps(thaw_json(frozen), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def timestamp(value: datetime | float) -> float:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ConfigurationError("expiry must be timezone-aware")
        result = value.timestamp()
    elif isinstance(value, bool):
        raise ConfigurationError("timestamp must be finite")
    elif isinstance(cast(object, value), (int, float)):
        result = float(value)
    else:
        raise ConfigurationError("timestamp must be numeric or timezone-aware")
    if not math.isfinite(result):
        raise ConfigurationError("timestamp must be finite")
    return result


@dataclass(frozen=True)
class IdleConversationKey:
    namespace: str
    bot_id: int
    chat_id: int
    user_id: int
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(cast(object, self.namespace), str)
            or not self.namespace
            or len(self.namespace) > 128
        ):
            raise UnsupportedContext("namespace must contain 1 to 128 characters")
        _utf8(self.namespace, "namespace")
        if self.tenant_id is not None:
            if not isinstance(cast(object, self.tenant_id), str):
                raise UnsupportedContext("invalid tenant scope")
            _utf8(self.tenant_id, "tenant_id")
        if any(
            isinstance(value, bool) or not isinstance(cast(object, value), int) or value <= 0
            for value in (self.bot_id, self.chat_id, self.user_id)
        ):
            raise UnsupportedContext("private identity requires positive integer IDs")
        if self.chat_id != self.user_id:
            raise UnsupportedContext("only actor-owned private chats are supported")
        if self.tenant_id is not None and (not self.tenant_id or len(self.tenant_id) > 128):
            raise UnsupportedContext("invalid tenant scope")


@dataclass(frozen=True)
class SessionGuard:
    session_id: str
    revision: int

    def __post_init__(self) -> None:
        _identifier(self.session_id, "session_id")
        _revision(self.revision)


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    expires_at: float
    revision: int = 1

    def __post_init__(self) -> None:
        _identifier(self.session_id, "session_id")
        _revision(self.revision)
        timestamp(self.expires_at)

    @property
    def guard(self) -> SessionGuard:
        return SessionGuard(self.session_id, self.revision)


@dataclass(frozen=True)
class ActivityGuard:
    session_id: str
    activity_id: str
    activity_revision: int

    def __post_init__(self) -> None:
        _identifier(self.session_id, "session_id")
        _identifier(self.activity_id, "activity_id")
        _revision(self.activity_revision)


@dataclass(frozen=True)
class ActivitySnapshot:
    session_id: str
    activity_id: str
    activity_key: str
    activity_revision: int
    policy_id: str
    adapter_key: str
    params: JsonObject
    entered_at: float
    last_activity_at: float
    expires_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", freeze_object(self.params))
        if not all(
            (self.session_id, self.activity_id, self.activity_key, self.policy_id, self.adapter_key)
        ):
            raise ConfigurationError("activity identifiers cannot be empty")
        _revision(self.activity_revision)
        for value in (
            self.session_id,
            self.activity_id,
            self.activity_key,
            self.policy_id,
            self.adapter_key,
        ):
            _identifier(value, "activity identifier")
        for value in (self.entered_at, self.last_activity_at, self.expires_at):
            timestamp(value)

    @property
    def guard(self) -> ActivityGuard:
        return ActivityGuard(self.session_id, self.activity_id, self.activity_revision)


class Phase(str, Enum):
    DISARMED = "disarmed"
    ACTIVE = "active"
    PROMPT_PENDING = "prompt_pending"
    PROMPTED = "prompted"
    DELIVERY_UNKNOWN = "delivery_unknown"
    RESUMING = "resuming"
    ABANDONING = "abandoning"
    RESTORING = "restoring"
    EFFECT_UNKNOWN = "effect_unknown"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class MessageRef:
    chat_id: int
    message_id: int


@dataclass(frozen=True)
class PendingOperation:
    operation_id: str
    kind: str
    stage: str = "reserved"
    started_at: float = 0
    attempts: int = 0
    effects: JsonObject = field(default_factory=empty_object)
    action_receipt: ActionReceipt | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effects", freeze_object(self.effects, max_bytes=8_388_608))


@dataclass(frozen=True)
class IdleSnapshot:
    phase: Phase = Phase.DISARMED
    deadline: float | None = None
    prompt: PromptReceipt | None = None
    operation: PendingOperation | None = None
    attempts: int = 0
    retry_at: float | None = None


@dataclass(frozen=True)
class RuntimeSnapshot:
    key: IdleConversationKey
    session: SessionSnapshot
    activity: ActivitySnapshot | None = None
    idle: IdleSnapshot = field(default_factory=IdleSnapshot)
    store_version: int = 1
    recovery_until: float = 0
    components: JsonObject = field(default_factory=empty_object)

    def __post_init__(self) -> None:
        object.__setattr__(self, "components", freeze_object(self.components, max_bytes=8_388_608))

    @property
    def version(self) -> int:
        return self.store_version


RuntimeRecord = RuntimeSnapshot


@dataclass(frozen=True)
class ActivitySpec:
    activity_key: str
    policy_id: str
    adapter_key: str
    params: JsonObject = field(default_factory=empty_object)
    expires_at: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", freeze_object(self.params))
        for value in (self.activity_key, self.policy_id, self.adapter_key):
            _identifier(value, "replacement activity identifier")
        if self.expires_at is not None:
            timestamp(self.expires_at)


@dataclass(frozen=True)
class FlowEligibility:
    resumable: bool = True
    authorized: bool = True
    expires_at: float | None = None
    recovery_kind: str = "restore"

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.resumable), bool) or not isinstance(
            cast(object, self.authorized), bool
        ):
            raise ConfigurationError("eligibility flags must be booleans")
        if self.expires_at is not None:
            timestamp(self.expires_at)


@dataclass(frozen=True)
class ActionReceipt:
    operation_id: str = ""
    disposition: str = "rearm"
    replacement: ActivitySpec | None = None
    details: JsonObject = field(default_factory=empty_object)
    component_updates: JsonObject = field(default_factory=empty_object)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", freeze_object(self.details))
        object.__setattr__(
            self, "component_updates", freeze_object(self.component_updates, max_bytes=8_388_608)
        )
        if self.disposition not in {"rearm", "disarm", "replacement"}:
            raise ConfigurationError("unknown adapter disposition")
        if (self.disposition == "replacement") != (self.replacement is not None):
            raise ConfigurationError("replacement disposition requires replacement activity")


@dataclass(frozen=True)
class FlowContext:
    key: IdleConversationKey
    activity: ActivitySnapshot
    operation_id: str
    now: float
    prompt_id: str | None = None
    bot: Bot | None = None
    dependencies: Mapping[str, object] = field(default_factory=empty_object)
    effects: EffectRecorder | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependencies", MappingProxyType(dict(self.dependencies)))


@dataclass(frozen=True)
class ConfigManifest:
    generation: str
    enabled: bool
    policies_digest: str


@dataclass(frozen=True)
class ConfigUpdate:
    enabled: bool
    operation_id: str

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.enabled), bool):
            raise ConfigurationError("enabled must be a boolean")
        if not self.operation_id or len(self.operation_id) > 256:
            raise ConfigurationError("operation_id must contain 1 to 256 characters")


@dataclass(frozen=True)
class IdleEvent:
    event_id: str
    operation_id: str
    outcome: str
    key: IdleConversationKey
    activity_key: str
    at: float
    prompt_id: str | None = None


@dataclass(frozen=True)
class PollReport:
    claimed: int = 0
    completed: int = 0
    failed: int = 0


@dataclass(frozen=True)
class ReconcileReport:
    inspected: int = 0
    repaired: int = 0
    pruned: int = 0


IdleStatus = RuntimeSnapshot
