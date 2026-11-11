"""Explicit staged activation; no migration invokes application effects."""

from __future__ import annotations

# Backend mixin implements the private storage protocol, like ComponentTransactions.
# pyright: reportPrivateUsage=false
import asyncio
from dataclasses import dataclass
from typing import Protocol, cast

from ..errors import ConfigurationMismatch, OperationIdConflict
from ..models import IdleConversationKey, RuntimeSnapshot
from ..protocols import Coordinator
from .queue import DeadlineQueue


@dataclass(frozen=True)
class StorageActivation:
    previous: int
    target: int
    changed: bool
    dry_run: bool
    records: int | None = None
    active_claims: int | None = None
    unresolved: int | None = None


def validate_activation(
    *, expected: int, target: int, operation_id: str, old_workers_drained: bool, dry_run: bool
) -> None:
    if (
        type(expected) is not int
        or expected not in (1, 2)
        or type(target) is not int
        or target != expected + 1
    ):
        raise ConfigurationMismatch(
            "Only explicit next storage format activation (1 to 2 or 2 to 3) is supported"
        )
    if (
        not isinstance(cast(object, operation_id), str)
        or not operation_id
        or len(operation_id) > 256
    ):
        raise ValueError("Storage activation operation ID must contain 1 to 256 characters")
    if type(dry_run) is not bool or type(old_workers_drained) is not bool:
        raise ValueError("Storage activation flags must be boolean")
    if not dry_run and not old_workers_drained:
        raise ConfigurationMismatch("Drain all 0.1 writers and workers before activation")


class FormatOwner(Protocol):
    _storage_format: int
    _activation_operation: str | None
    _lock: asyncio.Lock
    _records: dict[IdleConversationKey, RuntimeSnapshot]
    _queue: DeadlineQueue
    coordinator: Coordinator

    def _now(self) -> float: ...


class StorageFormats:
    """Single-process format state; authoritative Redis uses a persisted marker."""

    async def storage_format(self: FormatOwner) -> int:
        return self._storage_format

    async def require_storage_format(self: FormatOwner, version: int) -> None:
        if type(version) is not int or (
            self._storage_format != version and not (version == 2 and self._storage_format == 3)
        ):
            raise ConfigurationMismatch("Requested feature requires activated storage format")

    async def activate_storage_format(
        self: FormatOwner,
        *,
        operation_id: str,
        expected: int = 1,
        target: int = 2,
        old_workers_drained: bool = False,
        dry_run: bool = True,
    ) -> StorageActivation:
        validate_activation(
            expected=expected,
            target=target,
            operation_id=operation_id,
            old_workers_drained=old_workers_drained,
            dry_run=dry_run,
        )
        async with self._lock:
            active = sum(
                job.token is not None and job.lease_until > self._now()
                for job in self._queue.jobs.values()
            )
            unresolved = sum(record.idle.operation is not None for record in self._records.values())
            if self._activation_operation is not None and self._storage_format == target:
                if self._activation_operation != operation_id:
                    raise OperationIdConflict("Storage format was activated by another operation")
                return StorageActivation(
                    expected, target, False, dry_run, len(self._records), active, unresolved
                )
            if self._storage_format != expected:
                raise ConfigurationMismatch("Storage format changed before activation")
            if not dry_run:
                if active or self.coordinator.active_scopes:
                    raise ConfigurationMismatch("Protected work must drain before activation")
                self._storage_format = target
                self._activation_operation = operation_id
            return StorageActivation(
                expected, target, not dry_run, dry_run, len(self._records), active, unresolved
            )
