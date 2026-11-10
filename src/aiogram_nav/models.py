"""Immutable navigation contracts; all persisted times are epoch milliseconds."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, cast

from aiogram import Bot

from .errors import UnsupportedContext
from .json import JsonObject, JsonValue, empty_object, freeze_json, freeze_object, identifier

if TYPE_CHECKING:
    from .protocols import EffectRecorder

HistoryMode = Literal["push", "replace", "none", "pop", "clear"]
ActionKind = Literal["go", "back", "home", "cancel", "refresh", "track", "touch"]
ParameterValidator = Callable[[JsonObject], Mapping[str, object]]


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer at least {minimum}")


@dataclass(frozen=True)
class ConversationKey:
    namespace: str
    bot_id: int
    chat_id: int
    user_id: int
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        identifier(self.namespace, "namespace")
        for name in ("bot_id", "chat_id", "user_id"):
            _integer(getattr(self, name), name, 1)
        if self.chat_id != self.user_id:
            raise UnsupportedContext("Only actor-owned private conversations are supported")
        if self.tenant_id is not None:
            identifier(self.tenant_id, "tenant_id")


@dataclass(frozen=True)
class Node:
    id: str
    parent: str | None = None
    renderer: str | None = None
    back_to: str | None = None
    cancel_to: str | None = None
    validator: ParameterValidator | None = None
    metadata: JsonObject = field(default_factory=empty_object)

    def __post_init__(self) -> None:
        identifier(self.id, "node ID")
        for name in ("parent", "renderer", "back_to", "cancel_to"):
            value = getattr(self, name)
            if value is not None:
                identifier(value, name)
        if self.validator is not None and not callable(self.validator):
            raise ValueError("validator must be callable")
        object.__setattr__(self, "metadata", freeze_object(self.metadata))


@dataclass(frozen=True)
class MessageRef:
    chat_id: int
    message_id: int
    role: Literal["content", "controls", "tray"] = "content"

    def __post_init__(self) -> None:
        _integer(self.chat_id, "chat_id", 1)
        _integer(self.message_id, "message_id", 1)
        if self.role not in {"content", "controls", "tray"}:
            raise ValueError("Unsupported message role")


@dataclass(frozen=True)
class RenderResult:
    view_id: str
    messages: tuple[MessageRef, ...] = ()
    reply_keyboard_key: str | None = None
    locale: str = "en"
    reply_keyboard_locale: str | None = None

    def __post_init__(self) -> None:
        identifier(self.view_id, "view_id")
        identifier(self.locale, "locale")
        if self.reply_keyboard_locale is not None:
            identifier(self.reply_keyboard_locale, "reply_keyboard_locale")
        object.__setattr__(self, "messages", tuple(self.messages))
        if any(not isinstance(cast(object, ref), MessageRef) for ref in self.messages):
            raise ValueError("Messages must contain MessageRef values")
        if self.reply_keyboard_key is not None:
            identifier(self.reply_keyboard_key, "reply_keyboard_key")


@dataclass(frozen=True)
class ViewState(RenderResult):
    render_status: Literal["complete", "pending", "partial", "unknown"] = "complete"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.render_status not in {"complete", "pending", "partial", "unknown"}:
            raise ValueError("Unsupported render status")


@dataclass(frozen=True)
class HistoryEntry:
    node_id: str
    params: JsonObject = field(default_factory=empty_object)

    def __post_init__(self) -> None:
        identifier(self.node_id, "node_id")
        object.__setattr__(self, "params", freeze_object(self.params))


@dataclass(frozen=True)
class NavigationSnapshot:
    session_id: str
    node_id: str
    params: JsonObject
    nav_revision: int
    activity_revision: int
    entered_at: int
    last_activity_at: int
    expires_at: int
    view: ViewState
    history: tuple[HistoryEntry, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        identifier(self.session_id, "session_id")
        identifier(self.node_id, "node_id")
        object.__setattr__(self, "params", freeze_object(self.params))
        for name in ("nav_revision", "activity_revision"):
            _integer(getattr(self, name), name, 1)
        for name in ("entered_at", "last_activity_at", "expires_at"):
            _integer(getattr(self, name), name)
        if self.expires_at <= self.entered_at or self.last_activity_at >= self.expires_at:
            raise ValueError("Snapshot times are inconsistent")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Unsupported snapshot schema")
        if not isinstance(cast(object, self.view), ViewState):
            raise ValueError("Snapshot view must be ViewState")
        object.__setattr__(self, "history", tuple(self.history))
        if len(self.history) > 1000 or any(
            not isinstance(cast(object, item), HistoryEntry) for item in self.history
        ):
            raise ValueError("Invalid history")


@dataclass(frozen=True)
class VersionedSnapshot:
    snapshot: NavigationSnapshot
    version: str

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.snapshot), NavigationSnapshot):
            raise ValueError("Versioned snapshot requires a NavigationSnapshot")
        identifier(self.version, "version")


@dataclass(frozen=True)
class NavigationAction:
    kind: ActionKind = "go"
    target: str | None = None
    params: JsonObject = field(default_factory=empty_object)

    def __post_init__(self) -> None:
        if self.kind not in {"go", "back", "home", "cancel", "refresh", "track", "touch"}:
            raise ValueError("Unsupported navigation action")
        if self.target is not None:
            identifier(self.target, "target")
        object.__setattr__(self, "params", freeze_object(self.params))


@dataclass(frozen=True)
class NavigationIntent:
    operation_id: str
    node_id: str
    params: JsonObject = field(default_factory=empty_object)
    action: ActionKind = "go"
    history: HistoryMode = "push"
    source: str = "application"
    accepted_activity: bool = True
    expires_at: int | None = None
    expected_session_id: str | None = None
    view_id: str | None = None
    history_pop: int = 1

    def __post_init__(self) -> None:
        identifier(self.operation_id, "operation_id")
        identifier(self.node_id, "node_id")
        identifier(self.source, "source")
        NavigationAction(self.action)
        _integer(self.history_pop, "history_pop")
        if self.history_pop > 1000:
            raise ValueError("history_pop exceeds bounded history")
        if self.history not in {"push", "replace", "none", "pop", "clear"}:
            raise ValueError("Unsupported history mode")
        if not isinstance(cast(object, self.accepted_activity), bool):
            raise ValueError("accepted_activity must be boolean")
        for value in (self.expected_session_id, self.view_id):
            if value is not None:
                identifier(value)
        if self.expires_at is not None:
            _integer(self.expires_at, "expires_at", 1)
        object.__setattr__(self, "params", freeze_object(self.params))


@dataclass(frozen=True)
class EffectCheckpoint:
    stage: str
    state: Literal["started", "confirmed", "not_sent", "unknown"]
    result: JsonValue | RenderResult | None = None

    def __post_init__(self) -> None:
        identifier(self.stage, "stage")
        if self.state not in {"started", "confirmed", "not_sent", "unknown"}:
            raise ValueError("Unsupported effect state")
        if not isinstance(self.result, RenderResult):
            object.__setattr__(self, "result", freeze_json(self.result))


@dataclass(frozen=True)
class PreparedAction:
    key: ConversationKey
    intent: NavigationIntent
    session_id: str
    view_id: str
    expected_version: str | None
    expires_at: int
    prepared_at: int
    fingerprint: str
    status: Literal["prepared", "completed", "unknown", "failed"] = "prepared"
    effects: Mapping[str, EffectCheckpoint] = field(
        default_factory=lambda: dict[str, EffectCheckpoint]()
    )
    rendered: RenderResult | None = None

    def __post_init__(self) -> None:
        identifier(self.session_id, "session_id")
        identifier(self.view_id, "view_id")
        identifier(self.fingerprint, "fingerprint")
        _integer(self.expires_at, "expires_at", 1)
        _integer(self.prepared_at, "prepared_at")
        if self.status not in {"prepared", "completed", "unknown", "failed"}:
            raise ValueError("Unsupported action status")
        from types import MappingProxyType

        copied = dict(self.effects)
        if any(
            not isinstance(cast(object, item), EffectCheckpoint) or name != item.stage
            for name, item in copied.items()
        ):
            raise ValueError("Effect names must match stage identity")
        object.__setattr__(self, "effects", MappingProxyType(copied))

    @property
    def operation_id(self) -> str:
        return self.intent.operation_id

    @property
    def node_id(self) -> str:
        return self.intent.node_id

    @property
    def params(self) -> JsonObject:
        return self.intent.params


@dataclass(frozen=True)
class NavigationMutation:
    operation_id: str
    expected_session_id: str
    rendered: RenderResult | None = None
    kind: Literal["complete", "touch"] = "complete"
    accepted_activity: bool = True
    source: str = "application"

    def __post_init__(self) -> None:
        identifier(self.operation_id, "operation_id")
        identifier(self.expected_session_id, "expected_session_id")
        identifier(self.source, "source")
        if self.rendered is not None and not isinstance(cast(object, self.rendered), RenderResult):
            raise ValueError("Mutation rendering must be a RenderResult")
        if self.kind not in {"complete", "touch"} or not isinstance(
            cast(object, self.accepted_activity), bool
        ):
            raise ValueError("Invalid mutation")


@dataclass(frozen=True)
class CommitResult:
    snapshot: NavigationSnapshot
    version: str
    duplicate: bool = False

    def __post_init__(self) -> None:
        identifier(self.version, "version")


@dataclass(frozen=True)
class ActionStatus:
    status: Literal["not_found", "prepared", "completed", "unknown", "failed"]
    prepared: PreparedAction | None = None
    result: CommitResult | None = None


@dataclass(frozen=True)
class NavigationToken:
    token: str
    key: ConversationKey
    actor_id: int
    session_id: str
    view_id: str
    action: NavigationAction
    expires_at: int
    entry_id: str | None = None

    def __post_init__(self) -> None:
        identifier(self.token, "token")
        if not isinstance(cast(object, self.key), ConversationKey) or not isinstance(
            cast(object, self.action), NavigationAction
        ):
            raise ValueError("Control requires a conversation and navigation action")
        if self.entry_id is not None:
            identifier(self.entry_id, "entry_id")
        if len(self.token) > 48:
            raise ValueError("Control token exceeds callback capacity")
        _integer(self.actor_id, "actor_id", 1)
        if self.actor_id != self.key.user_id:
            raise UnsupportedContext("Control actor differs from conversation owner")
        identifier(self.session_id, "session_id")
        identifier(self.view_id, "view_id")
        _integer(self.expires_at, "expires_at", 1)


@dataclass(frozen=True)
class RenderRequest:
    key: ConversationKey
    operation_id: str
    node: Node
    params: JsonObject
    view_id: str
    session_id: str
    current: NavigationSnapshot | None = None
    locale: str = "en"
    bot: Bot | None = None
    dependencies: Mapping[str, object] = field(default_factory=lambda: dict[str, object]())
    effects: EffectRecorder | None = None
    delivery: Literal["auto", "send", "edit"] = "auto"
    expires_at: int | None = None

    def __post_init__(self) -> None:
        identifier(self.operation_id, "operation_id")
        identifier(self.view_id, "view_id")
        identifier(self.session_id, "session_id")
        identifier(self.locale, "locale")
        object.__setattr__(self, "params", freeze_object(self.params))
        from types import MappingProxyType

        object.__setattr__(self, "dependencies", MappingProxyType(dict(self.dependencies)))

    @property
    def node_id(self) -> str:
        return self.node.id

    @property
    def target(self) -> str:
        return self.node.id


@dataclass(frozen=True)
class NavigationEvent:
    operation_id: str
    key: ConversationKey
    old_node: str | None
    new_node: str
    nav_revision: int
    activity_revision: int
    source: str
    outcome: str
    at: int
