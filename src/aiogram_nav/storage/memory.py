"""Single-process navigation state, conditional receipts and render reservations."""

from __future__ import annotations

import asyncio
import math
import secrets
from dataclasses import replace

from ..clock import Clock, SystemClock
from ..config import NavigationConfig
from ..errors import (
    ConfigurationError,
    OperationIdConflict,
    Overloaded,
    OwnershipLost,
    PendingAction,
    RenderUnknown,
    SessionExpired,
    StaleView,
    VersionConflict,
)
from ..isolation import MemoryCoordinator
from ..json import freeze_object
from ..models import (
    ActionStatus,
    CommitResult,
    ConversationKey,
    EffectCheckpoint,
    HistoryEntry,
    NavigationIntent,
    NavigationMutation,
    NavigationSnapshot,
    PreparedAction,
    RenderResult,
    VersionedSnapshot,
    ViewState,
)
from ..protocols import Coordinator
from .state import Conversation, Operation, fingerprint, payload_size
from .tokens import MemoryTokens


class MemoryNavigationRepository(MemoryTokens):
    """One event loop/process only. No persistence or recovery across restart."""

    capabilities = frozenset({"conditional_commits", "prepared_actions", "opaque_tokens"})

    def __init__(
        self, *, clock: Clock | None = None, config: NavigationConfig | None = None
    ) -> None:
        self.clock = clock or SystemClock()
        self.config = config or NavigationConfig()
        self.coordinator: Coordinator = MemoryCoordinator()
        self._lock = asyncio.Lock()
        self._records: dict[ConversationKey, Conversation] = {}
        self._sweep_cursor = 0

    def bind_coordinator(self, coordinator: Coordinator) -> None:
        if coordinator is self.coordinator:
            return
        if self._records or self.coordinator.active_scopes or coordinator.active_scopes:
            raise ConfigurationError("Configure shared navigation isolation before activity")
        self.coordinator = coordinator

    def _guard_scope(self, key: ConversationKey, scope: object | None) -> None:
        if scope is not None and not self.coordinator.scope_matches(key, scope):
            raise OwnershipLost("Navigation coordination capability is expired or foreign")

    def _now(self) -> int:
        return self.clock.now()

    def _changed(self, record: Conversation) -> None:
        record.version = secrets.token_urlsafe(16)
        if record.current is not None:
            record.current = VersionedSnapshot(record.current.snapshot, record.version)

    def _prune(self, record: Conversation) -> None:
        now = self._now()
        bindings: set[tuple[str, str]] = set()
        if record.current is not None and record.current.snapshot.expires_at > now:
            view = record.current.snapshot
            bindings.add((view.session_id, view.view.view_id))
        pending = record.operations.get(record.pending_id) if record.pending_id else None
        if pending is not None and pending.prepared is not None:
            bindings.add((pending.prepared.session_id, pending.prepared.view_id))
        for token, entry in tuple(record.tokens.items()):
            if (
                entry.token.expires_at <= now
                or (entry.token.session_id, entry.token.view_id) not in bindings
            ):
                del record.tokens[token]
        for operation_id, entry in tuple(record.operations.items()):
            if entry.status in {"completed", "failed"} and entry.retention_until <= now:
                del record.operations[operation_id]

    def _removable(self, record: Conversation) -> bool:
        self._prune(record)
        return (
            (record.current is None or record.current.snapshot.expires_at <= self._now())
            and not record.operations
            and not record.tokens
            and record.pending_id is None
        )

    def _admit(self, key: ConversationKey) -> Conversation:
        record = self._records.get(key)
        if record is not None:
            self._prune(record)
            return record
        if len(self._records) >= self.config.max_conversations:
            for old_key, old_record in tuple(self._records.items()):
                if self._removable(old_record):
                    del self._records[old_key]
            if len(self._records) >= self.config.max_conversations:
                raise Overloaded("Retained navigation conversation capacity exhausted")
        record = Conversation(secrets.token_urlsafe(16))
        self._records[key] = record
        return record

    def _operation(self, record: Conversation, operation_id: str) -> Operation:
        entry = record.operations.get(operation_id)
        if entry is None or entry.prepared is None:
            raise OwnershipLost("Navigation operation no longer exists")
        return entry

    def _current(self, record: Conversation) -> VersionedSnapshot | None:
        current = record.current
        return (
            current if current is not None and current.snapshot.expires_at > self._now() else None
        )

    async def load(self, key: ConversationKey) -> VersionedSnapshot | None:
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                return None
            self._prune(record)
            return self._current(record)

    async def prepare(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        intent: NavigationIntent,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
        freeze_object(intent.params, max_bytes=self.config.max_params_bytes)
        digest = fingerprint(intent)
        async with self._lock:
            self._guard_scope(key, coordination_scope)
            record = self._admit(key)
            previous = record.operations.get(intent.operation_id)
            if previous is not None:
                if previous.fingerprint != digest:
                    raise OperationIdConflict("Navigation operation ID has different intent")
                if previous.prepared is None:
                    raise OperationIdConflict("Operation ID belongs to a state-only mutation")
                return previous.prepared
            if len(record.operations) >= self.config.max_receipts:
                raise Overloaded("Navigation operation receipt capacity exhausted")
            if record.pending_id is not None:
                raise PendingAction("A navigation render must be recovered first")
            current = self._current(record)
            if (current.version if current else None) != expected_version:
                raise VersionConflict("Navigation state changed before prepare")
            snapshot = current.snapshot if current else None
            if intent.expected_session_id is not None and (
                snapshot is None or snapshot.session_id != intent.expected_session_id
            ):
                raise SessionExpired("Navigation session generation changed")
            now = self._now()
            expiry = (
                snapshot.expires_at
                if snapshot
                else (intent.expires_at or now + math.ceil(self.config.session_seconds * 1000))
            )
            if expiry <= now or (
                snapshot is not None
                and intent.expires_at is not None
                and intent.expires_at != expiry
            ):
                raise SessionExpired("Navigation expiry cannot be extended")
            view_id = getattr(intent, "view_id", None) if intent.action == "track" else None
            if (
                view_id is not None
                and snapshot is not None
                and (
                    snapshot.view.view_id == view_id
                    or any(
                        item.prepared is not None
                        and item.prepared.session_id == snapshot.session_id
                        and item.prepared.view_id == view_id
                        for item in record.operations.values()
                    )
                )
            ):
                raise StaleView("Tracking a new action requires a fresh view generation")
            prepared = PreparedAction(
                key=key,
                intent=intent,
                session_id=snapshot.session_id if snapshot else secrets.token_urlsafe(18),
                view_id=view_id or secrets.token_urlsafe(18),
                expected_version=expected_version,
                expires_at=expiry,
                prepared_at=now,
                fingerprint=digest,
            )
            record.operations[intent.operation_id] = Operation(
                digest,
                prepared,
                retention_until=now + math.ceil(self.config.recovery_seconds * 1000),
            )
            record.pending_id = intent.operation_id
            self._changed(record)
            return prepared

    async def checkpoint(
        self,
        key: ConversationKey,
        *,
        operation_id: str,
        effect: EffectCheckpoint,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
        async with self._lock:
            self._guard_scope(key, coordination_scope)
            record = self._records.get(key)
            if record is None:
                raise OwnershipLost("Navigation reservation is absent")
            entry = self._operation(record, operation_id)
            prepared = entry.prepared
            assert prepared is not None
            if record.pending_id != operation_id or entry.status not in {"prepared", "unknown"}:
                raise OwnershipLost("Navigation reservation is no longer current")
            if prepared.expires_at <= self._now() and effect.state == "started":
                raise SessionExpired("Navigation authorization expired")
            if isinstance(effect.result, RenderResult) and any(
                ref.chat_id != key.chat_id for ref in effect.result.messages
            ):
                raise StaleView("Effect messages belong to another conversation")
            previous = prepared.effects.get(effect.stage)
            if previous is not None and fingerprint(previous) == fingerprint(effect):
                return prepared
            if previous is None and len(prepared.effects) >= self.config.max_receipts:
                raise Overloaded("Navigation effect stage capacity exhausted")
            if payload_size(effect.result) > self.config.max_params_bytes:
                raise Overloaded("Navigation effect receipt exceeds the payload limit")
            effects = dict(prepared.effects)
            if previous is not None:
                if previous.state == "confirmed":
                    raise OperationIdConflict("Confirmed navigation effect is immutable")
                if previous.state == "unknown" and effect.state != "confirmed":
                    raise RenderUnknown("An uncertain effect cannot be blindly repeated")
                if previous.state == "started" and effect.state == "started":
                    raise RenderUnknown("A started effect requires recovery evidence")
            elif effect.state == "confirmed":
                raise OwnershipLost("Effect intent must precede confirmation")
            effects[effect.stage] = effect
            status = (
                "unknown"
                if any(item.state == "unknown" for item in effects.values())
                else "prepared"
            )
            prepared = replace(prepared, effects=effects, status=status)
            entry.prepared, entry.status = prepared, status
            self._changed(record)
            return prepared

    async def lookup_operation(self, key: ConversationKey, *, operation_id: str) -> ActionStatus:
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                return ActionStatus("not_found")
            self._prune(record)
            entry = record.operations.get(operation_id)
            if entry is None:
                return ActionStatus("not_found")
            return ActionStatus(entry.status, entry.prepared, entry.result)

    def _complete(self, record: Conversation, mutation: NavigationMutation) -> CommitResult:
        entry = self._operation(record, mutation.operation_id)
        prepared = entry.prepared
        assert prepared is not None
        if record.pending_id != mutation.operation_id:
            raise OwnershipLost("Navigation reservation was superseded")
        if mutation.expected_session_id != prepared.session_id:
            raise SessionExpired("Navigation session generation changed")
        if prepared.expires_at <= self._now():
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
            and fingerprint(confirmed_render.result) != fingerprint(rendered)
        ):
            raise OperationIdConflict("Completion differs from the confirmed rendering receipt")
        if any(item.state in {"started", "unknown"} for item in prepared.effects.values()):
            raise RenderUnknown("Navigation effects remain unresolved")
        current = self._current(record)
        old = current.snapshot if current else None
        if old is not None and old.session_id != prepared.session_id:
            raise SessionExpired("Navigation session generation changed")
        params_changed = old is None or fingerprint(old.params) != fingerprint(prepared.params)
        history = old.history if old else ()
        mode = prepared.intent.history
        if (
            mode == "push"
            and old is not None
            and (old.node_id != prepared.node_id or params_changed)
        ):
            history = (*history, HistoryEntry(old.node_id, old.params))
        elif mode == "pop":
            amount = getattr(prepared.intent, "history_pop", 1)
            history = history[:-amount] if amount else history
        elif mode == "clear":
            history = ()
        limit = self.config.history_limit
        history = history[-limit:] if limit else ()
        now = self._now()
        accepted = prepared.intent.accepted_activity and mutation.accepted_activity
        snapshot = NavigationSnapshot(
            session_id=prepared.session_id,
            node_id=prepared.node_id,
            params=prepared.params,
            nav_revision=(old.nav_revision + 1) if old else 1,
            activity_revision=(old.activity_revision + int(accepted)) if old else 1,
            entered_at=now
            if old is None or old.node_id != prepared.node_id or params_changed
            else old.entered_at,
            last_activity_at=now if accepted or old is None else old.last_activity_at,
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
        self._changed(record)
        record.current = VersionedSnapshot(snapshot, record.version)
        result = CommitResult(snapshot, record.version)
        entry.result, entry.status = result, "completed"
        entry.completion_fingerprint = fingerprint(mutation)
        entry.prepared = replace(prepared, rendered=rendered, status="completed")
        entry.retention_until = now + math.ceil(self.config.recovery_seconds * 1000)
        self._prune(record)
        return result

    async def commit(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        mutation: NavigationMutation,
        coordination_scope: object | None = None,
    ) -> CommitResult:
        async with self._lock:
            self._guard_scope(key, coordination_scope)
            record = self._records.get(key)
            if record is None:
                raise SessionExpired("Navigation state is absent")
            self._prune(record)
            previous = record.operations.get(mutation.operation_id)
            if previous is not None and previous.status == "completed":
                if previous.result is None:
                    raise OwnershipLost("Completed operation has no receipt")
                if previous.completion_fingerprint != fingerprint(mutation):
                    raise OperationIdConflict("Completion operation ID has different input")
                # Completion retries must keep the same session and rendered intent.
                if previous.result.snapshot.session_id != mutation.expected_session_id or (
                    mutation.rendered is not None
                    and previous.prepared is not None
                    and fingerprint(previous.prepared.rendered) != fingerprint(mutation.rendered)
                ):
                    raise OperationIdConflict("Completion operation ID has different input")
                return replace(previous.result, duplicate=True)
            if mutation.kind == "complete":
                return self._complete(record, mutation)
            if mutation.kind != "touch":
                raise ValueError("Unknown navigation mutation kind")
            if previous is not None:
                raise OperationIdConflict("Operation ID belongs to another intent")
            if record.pending_id is not None:
                raise PendingAction("A navigation render must be recovered first")
            current = self._current(record)
            if current is None or current.snapshot.session_id != mutation.expected_session_id:
                raise SessionExpired("Navigation session is absent or expired")
            if current.version != expected_version:
                raise VersionConflict("Navigation state changed")
            if len(record.operations) >= self.config.max_receipts:
                raise Overloaded("Navigation operation receipt capacity exhausted")
            now = self._now()
            snapshot = replace(
                current.snapshot,
                activity_revision=current.snapshot.activity_revision
                + int(mutation.accepted_activity),
                last_activity_at=now
                if mutation.accepted_activity
                else current.snapshot.last_activity_at,
            )
            self._changed(record)
            record.current = VersionedSnapshot(snapshot, record.version)
            result = CommitResult(snapshot, record.version)
            record.operations[mutation.operation_id] = Operation(
                fingerprint(mutation),
                None,
                "completed",
                result,
                now + math.ceil(self.config.recovery_seconds * 1000),
                fingerprint(mutation),
            )
            return result

    async def pending(self, key: ConversationKey) -> PreparedAction | None:
        async with self._lock:
            record = self._records.get(key)
            if record is None or record.pending_id is None:
                return None
            return self._operation(record, record.pending_id).prepared

    async def mark_unknown(self, key: ConversationKey, *, operation_id: str) -> None:
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                raise OwnershipLost("Navigation reservation is absent")
            entry = self._operation(record, operation_id)
            if record.pending_id != operation_id:
                raise OwnershipLost("Navigation reservation is no longer current")
            entry.status = "unknown"
            assert entry.prepared is not None
            entry.prepared = replace(entry.prepared, status="unknown")
            self._changed(record)

    async def abandon(
        self, key: ConversationKey, operation_id: str, *, expected_session_id: str
    ) -> None:
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                raise OwnershipLost("Navigation reservation is absent")
            entry = self._operation(record, operation_id)
            assert entry.prepared is not None
            if entry.prepared.session_id != expected_session_id:
                raise SessionExpired("Navigation reservation session changed")
            if entry.status == "failed":
                return
            if record.pending_id != operation_id:
                raise OwnershipLost("Navigation reservation is no longer current")
            entry.status = "failed"
            entry.prepared = replace(entry.prepared, status="failed")
            entry.retention_until = self._now() + math.ceil(self.config.recovery_seconds * 1000)
            record.pending_id = None
            self._changed(record)

    async def sweep(self, *, limit: int = 100) -> int:
        if type(limit) is not int or limit <= 0:
            raise ValueError("Sweep limit must be a positive integer")
        async with self._lock:
            keys = list(self._records)
            if not keys:
                return 0
            start = self._sweep_cursor % len(keys)
            selected = (keys[start:] + keys[:start])[:limit]
            self._sweep_cursor = start + len(selected)
            pruned = 0
            for key in selected:
                if self._removable(self._records[key]):
                    del self._records[key]
                    pruned += 1
            return pruned

    async def close(self) -> None:
        """No caller-owned state is discarded by closing a memory repository."""
