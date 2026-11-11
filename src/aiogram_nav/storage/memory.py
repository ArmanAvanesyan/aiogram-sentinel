"""Single-process navigation state, conditional receipts and render reservations."""

from __future__ import annotations

import asyncio
import heapq
import math
import secrets
from dataclasses import replace

from ..clock import Clock, SystemClock
from ..config import NavigationConfig
from ..engine import EngineName
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
    NavigationIntent,
    NavigationMutation,
    PreparedAction,
    RenderResult,
    VersionedSnapshot,
)
from ..protocols import Coordinator
from .adoption import MemoryAdoption
from .completion import complete
from .sessions import MemorySessions
from .state import Conversation, Operation, fingerprint, payload_size
from .tokens import MemoryTokens


class MemoryNavigationRepository(MemoryAdoption, MemoryTokens, MemorySessions):
    """One event loop/process only. No persistence or recovery across restart."""

    @property
    def atomic_adoption(self) -> bool:
        # A subclass can explicitly opt in after auditing its public-method hooks.
        return type(self) is MemoryNavigationRepository

    capabilities = frozenset({"conditional_commits", "prepared_actions", "opaque_tokens"})

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        config: NavigationConfig | None = None,
        engine: EngineName | None = None,
        storage_format: int | None = None,
    ) -> None:
        self.clock = clock or SystemClock()
        self.config = config or NavigationConfig()
        if engine is not None:
            self.config = replace(self.config, engine=engine)
        self.coordinator: Coordinator = MemoryCoordinator()
        self.application_coordinator_selected = False
        self._lock = asyncio.Lock()
        self._records: dict[ConversationKey, Conversation] = {}
        self._sweep_cursor = 0
        if storage_format is not None and (
            type(storage_format) is not int or storage_format not in (1, 3)
        ):
            raise ConfigurationError("Fresh storage_format must be 1 or 3")
        self._storage_format = storage_format or 1
        self._format_operations: dict[str, tuple[int, int]] = {}

    def bind_coordinator(self, coordinator: Coordinator) -> None:
        if coordinator is self.coordinator:
            self.application_coordinator_selected = True
            return
        if self._records or self.coordinator.active_scopes or coordinator.active_scopes:
            raise ConfigurationError("Configure shared navigation isolation before activity")
        self.coordinator = coordinator
        self.application_coordinator_selected = True

    def _guard_scope(self, key: ConversationKey, scope: object | None) -> None:
        if scope is not None and not self.coordinator.scope_matches(key, scope):
            raise OwnershipLost("Navigation coordination capability is expired or foreign")

    def _fingerprint(self, value: object) -> str:
        return fingerprint(value, engine=self.config.engine)

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
        while record.expiry_heap and record.expiry_heap[0][0] <= now:
            expiry, operation_id = heapq.heappop(record.expiry_heap)
            entry = record.operations.get(operation_id)
            if (
                entry is not None
                and entry.status in {"completed", "failed"}
                and entry.retention_until == expiry
            ):
                if entry.prepared is not None:
                    pair = entry.prepared.session_id, entry.prepared.view_id
                    if record.views.get(pair) == operation_id:
                        record.views.pop(pair, None)
                del record.operations[operation_id]
        if len(record.expiry_heap) > 2 * len(record.operations) + 128:
            record.expiry_heap = [
                (entry.retention_until, operation_id)
                for operation_id, entry in record.operations.items()
                if entry.status in {"completed", "failed"}
            ]
            heapq.heapify(record.expiry_heap)

    def _removable(self, record: Conversation) -> bool:
        self._prune(record)
        return (
            (record.current is None or record.current.snapshot.expires_at <= self._now())
            and not record.operations
            and not record.unloaded_operations
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
        async with self._lock:
            return self._prepare_locked(
                key,
                expected_version=expected_version,
                intent=intent,
                coordination_scope=coordination_scope,
            )

    def _prepare_locked(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        intent: NavigationIntent,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
        freeze_object(intent.params, max_bytes=self.config.max_params_bytes)
        digest = self._fingerprint(intent)
        self._guard_scope(key, coordination_scope)
        record = self._admit(key)
        previous = record.operations.get(intent.operation_id)
        if previous is not None:
            if previous.fingerprint != digest:
                raise OperationIdConflict("Navigation operation ID has different intent")
            if previous.prepared is None:
                raise OperationIdConflict("Operation ID belongs to a state-only mutation")
            return previous.prepared
        if len(record.operations) + record.unloaded_operations >= self.config.max_receipts:
            raise Overloaded("Navigation operation receipt capacity exhausted")
        if record.pending_id is not None:
            raise PendingAction("A navigation render must be recovered first")
        current = self._current(record)
        if (current.version if current else None) != expected_version:
            raise VersionConflict("Navigation state changed before prepare")
        snapshot = current.snapshot if current else None
        bound = record.host_session
        if bound is not None and bound[1] <= self._now():
            raise SessionExpired(
                "Authoritative host generation expired; replace its generation explicitly"
            )
        if (
            bound is not None
            and snapshot is not None
            and (snapshot.session_id != bound[0] or snapshot.expires_at != bound[1])
        ):
            raise SessionExpired("Navigation differs from its authoritative host generation")
        chosen_session = snapshot.session_id if snapshot else bound[0] if bound else None
        if intent.expected_session_id is not None and (
            chosen_session != intent.expected_session_id
        ):
            raise SessionExpired("Navigation session generation changed")
        now = self._now()
        expiry = (
            snapshot.expires_at
            if snapshot
            else (
                bound[1]
                if bound is not None
                else record.external_session.absolute_expires_at
                if record.external_session
                else (intent.expires_at or now + math.ceil(self.config.session_seconds * 1000))
            )
        )
        if expiry <= now or (
            snapshot is not None and intent.expires_at is not None and intent.expires_at != expiry
        ):
            raise SessionExpired("Navigation expiry cannot be extended")
        view_id = getattr(intent, "view_id", None) if intent.action == "track" else None
        if view_id is not None and (
            (snapshot is not None and snapshot.view.view_id == view_id)
            or (chosen_session is not None and (chosen_session, view_id) in record.views)
        ):
            raise StaleView("Tracking a new action requires a fresh view generation")
        prepared = PreparedAction(
            key=key,
            intent=intent,
            session_id=chosen_session or secrets.token_urlsafe(18),
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
        record.views[(prepared.session_id, prepared.view_id)] = intent.operation_id
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
            return self._checkpoint_locked(
                key, operation_id=operation_id, effect=effect, coordination_scope=coordination_scope
            )

    def _checkpoint_locked(
        self,
        key: ConversationKey,
        *,
        operation_id: str,
        effect: EffectCheckpoint,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
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
        if previous is not None and self._fingerprint(previous) == self._fingerprint(effect):
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
            "unknown" if any(item.state == "unknown" for item in effects.values()) else "prepared"
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

    async def commit(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        mutation: NavigationMutation,
        coordination_scope: object | None = None,
    ) -> CommitResult:
        async with self._lock:
            return self._commit_locked(
                key,
                expected_version=expected_version,
                mutation=mutation,
                coordination_scope=coordination_scope,
            )

    def _commit_locked(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        mutation: NavigationMutation,
        coordination_scope: object | None = None,
    ) -> CommitResult:
        self._guard_scope(key, coordination_scope)
        record = self._records.get(key)
        if record is None:
            raise SessionExpired("Navigation state is absent")
        self._prune(record)
        previous = record.operations.get(mutation.operation_id)
        if previous is not None and previous.status == "completed":
            if previous.result is None:
                raise OwnershipLost("Completed operation has no receipt")
            if previous.completion_fingerprint != self._fingerprint(mutation):
                raise OperationIdConflict("Completion operation ID has different input")
            # Completion retries must keep the same session and rendered intent.
            if previous.result.snapshot.session_id != mutation.expected_session_id or (
                mutation.rendered is not None
                and previous.prepared is not None
                and self._fingerprint(previous.prepared.rendered)
                != self._fingerprint(mutation.rendered)
            ):
                raise OperationIdConflict("Completion operation ID has different input")
            return replace(previous.result, duplicate=True)
        if mutation.kind == "complete":
            return complete(self, record, mutation)
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
        if len(record.operations) + record.unloaded_operations >= self.config.max_receipts:
            raise Overloaded("Navigation operation receipt capacity exhausted")
        now = self._now()
        snapshot = replace(
            current.snapshot,
            activity_revision=current.snapshot.activity_revision + int(mutation.accepted_activity),
            last_activity_at=now
            if mutation.accepted_activity
            else current.snapshot.last_activity_at,
        )
        self._changed(record)
        record.current = VersionedSnapshot(snapshot, record.version)
        result = CommitResult(snapshot, record.version)
        record.operations[mutation.operation_id] = Operation(
            self._fingerprint(mutation),
            None,
            "completed",
            result,
            now + math.ceil(self.config.recovery_seconds * 1000),
            self._fingerprint(mutation),
        )
        heapq.heappush(
            record.expiry_heap,
            (record.operations[mutation.operation_id].retention_until, mutation.operation_id),
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
            heapq.heappush(record.expiry_heap, (entry.retention_until, operation_id))
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
