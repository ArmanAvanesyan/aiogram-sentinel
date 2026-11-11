"""Read-only application session bindings and explicit storage-format activation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast

from aiogram_coordination import ExternalSession, validate_session_transition

from ..errors import ConfigurationError, OperationIdConflict, PendingAction, SessionExpired
from ..json import identifier
from ..models import ConversationKey
from ..protocols import Coordinator
from .state import Conversation


@dataclass(frozen=True)
class StorageMigrationReport:
    before: int
    after: int
    applied: bool
    conversations: int
    pending: int


class MemorySessions:
    _storage_format: int
    _format_operations: dict[str, tuple[int, int]]
    _lock: asyncio.Lock
    _records: dict[ConversationKey, Conversation]
    coordinator: Coordinator

    def _admit(self, key: ConversationKey) -> Conversation:
        raise NotImplementedError

    def _changed(self, record: Conversation) -> None:
        raise NotImplementedError

    def _now(self) -> int:
        raise NotImplementedError

    @property
    def storage_format(self) -> int:
        return self._storage_format

    def require_storage_format(self, version: int) -> None:
        if type(version) is not int or version not in (1, 2, 3) or self.storage_format < version:
            raise ConfigurationError(
                "Explicitly activate storage format 2 after draining old workers"
            )

    async def activate_storage_format(
        self,
        *,
        expected: int = 1,
        target: int = 2,
        operation_id: str,
        old_workers_drained: bool = False,
        dry_run: bool = True,
    ) -> StorageMigrationReport:
        if (
            type(expected) is not int
            or type(target) is not int
            or (expected, target) not in ((1, 2), (1, 3), (2, 3))
        ):
            raise ConfigurationError(
                "Only explicit upgrades to a newer supported format are allowed"
            )
        if (
            not isinstance(cast(object, operation_id), str)
            or not operation_id
            or len(operation_id) > 256
            or type(dry_run) is not bool
            or type(old_workers_drained) is not bool
        ):
            raise ConfigurationError("Invalid storage activation arguments")
        try:
            identifier(operation_id, "operation_id")
        except ValueError as error:
            raise ConfigurationError(str(error)) from error
        async with self._lock:
            previous = self._format_operations.get(operation_id)
            if previous is not None and previous != (expected, target):
                raise OperationIdConflict("Activation operation ID has different intent")
            if self._storage_format != expected and previous is None and not dry_run:
                raise ConfigurationError("Storage format changed; review before retrying")
            report = StorageMigrationReport(
                self._storage_format,
                target,
                not dry_run,
                len(self._records),
                sum(record.pending_id is not None for record in self._records.values()),
            )
            if dry_run:
                return report
            if not old_workers_drained or self.coordinator.active_scopes:
                raise ConfigurationError("Drain all old writers and local scopes before activation")
            self._storage_format = target
            self._format_operations[operation_id] = (expected, target)
            return report

    async def external_session(self, key: ConversationKey) -> ExternalSession | None:
        async with self._lock:
            record = self._records.get(key)
            return record.external_session if record is not None else None

    async def bind_external_session(
        self,
        key: ConversationKey,
        session: ExternalSession,
        *,
        coordination_scope: object | None = None,
    ) -> None:
        self.require_storage_format(2)
        if not isinstance(cast(object, session), ExternalSession) or not session.is_live(
            self._now()
        ):
            raise SessionExpired("Application session is not authorized")
        if coordination_scope is not None and not self.coordinator.scope_matches(
            key, coordination_scope
        ):
            from ..errors import OwnershipLost

            raise OwnershipLost("Session binding scope is expired or foreign")
        async with self._lock:
            record = self._admit(key)
            previous = record.external_session
            if previous is not None:
                try:
                    validate_session_transition(previous, session)
                except ValueError as error:
                    raise ConfigurationError(str(error)) from error
            changed = previous is None or previous.session_id != session.session_id
            if changed and record.pending_id is not None:
                raise PendingAction("Resolve the old session's pending effects before rebinding")
            if changed:
                record.current = None
                record.host_session = None
                record.tokens.clear()
            binding = ExternalSession(
                session.session_id, session.revision, session.absolute_expires_at
            )
            if binding != previous:
                record.external_session = binding
                self._changed(record)
