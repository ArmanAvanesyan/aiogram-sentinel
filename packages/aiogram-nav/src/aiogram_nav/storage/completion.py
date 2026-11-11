"""Pure completion reducer; ownership and external effects stay outside this module."""

from __future__ import annotations

# Internal pure reducer intentionally uses the repository implementation protocol.
# pyright: reportPrivateUsage=false
import heapq
import math
from dataclasses import replace
from typing import Protocol

from ..config import NavigationConfig
from ..errors import OperationIdConflict, OwnershipLost, RenderUnknown, SessionExpired, StaleView
from ..models import (
    CommitResult,
    NavigationMutation,
    NavigationSnapshot,
    VersionedSnapshot,
    ViewState,
)
from .state import Conversation, Operation
from .transition import transition


class CompletionOwner(Protocol):
    config: NavigationConfig

    def _operation(self, record: Conversation, operation_id: str) -> Operation: ...
    def _now(self) -> int: ...
    def _current(self, record: Conversation) -> VersionedSnapshot | None: ...
    def _changed(self, record: Conversation) -> None: ...
    def _prune(self, record: Conversation) -> None: ...
    def _fingerprint(self, value: object) -> str: ...


def complete(
    owner: CompletionOwner, record: Conversation, mutation: NavigationMutation
) -> CommitResult:
    entry = owner._operation(record, mutation.operation_id)
    prepared = entry.prepared
    assert prepared is not None
    if record.pending_id != mutation.operation_id:
        raise OwnershipLost("Navigation reservation was superseded")
    if mutation.expected_session_id != prepared.session_id:
        raise SessionExpired("Navigation session generation changed")
    if prepared.expires_at <= owner._now():
        raise SessionExpired("Navigation authorization expired")
    rendered = mutation.rendered
    if rendered is None or rendered.view_id != prepared.view_id:
        raise StaleView("Rendered view does not match the reservation")
    if any(ref.chat_id != prepared.key.chat_id for ref in rendered.messages):
        raise StaleView("Rendered messages belong to another conversation")
    if isinstance(rendered, ViewState) and rendered.render_status != "complete":
        raise RenderUnknown("A partial view cannot complete navigation")
    confirmed_render = prepared.effects.get("render")
    if (
        confirmed_render is not None
        and confirmed_render.state == "confirmed"
        and owner._fingerprint(confirmed_render.result) != owner._fingerprint(rendered)
    ):
        raise OperationIdConflict("Completion differs from the confirmed rendering receipt")
    if any(item.state in {"started", "unknown"} for item in prepared.effects.values()):
        raise RenderUnknown("Navigation effects remain unresolved")
    current = owner._current(record)
    old = current.snapshot if current else None
    if old is not None and old.session_id != prepared.session_id:
        raise SessionExpired("Navigation session generation changed")
    now = owner._now()
    history, state = transition(
        old, prepared, mutation, config=owner.config, now=now, fingerprint=owner._fingerprint
    )
    snapshot = NavigationSnapshot(
        session_id=prepared.session_id,
        node_id=prepared.node_id,
        params=prepared.params,
        nav_revision=state["nav_revision"],
        activity_revision=state["activity_revision"],
        entered_at=state["entered_at"],
        last_activity_at=state["last_activity_at"],
        expires_at=prepared.expires_at,
        view=ViewState(
            rendered.view_id,
            rendered.messages,
            rendered.reply_keyboard_key,
            rendered.locale,
            rendered.reply_keyboard_locale,
        ),
        history=history,
    )
    record.pending_id = None
    owner._changed(record)
    record.current = VersionedSnapshot(snapshot, record.version)
    result = CommitResult(snapshot, record.version)
    entry.result, entry.status = result, "completed"
    entry.completion_fingerprint = owner._fingerprint(mutation)
    entry.prepared = replace(prepared, rendered=rendered, status="completed")
    entry.retention_until = now + math.ceil(owner.config.recovery_seconds * 1000)
    heapq.heappush(record.expiry_heap, (entry.retention_until, mutation.operation_id))
    owner._prune(record)
    return result
