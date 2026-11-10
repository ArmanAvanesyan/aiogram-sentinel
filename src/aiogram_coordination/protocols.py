"""Task-scoped coordination, fencing and verifiable FSM isolation contracts."""

from __future__ import annotations

from collections.abc import Hashable
from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable

from aiogram.fsm.storage.base import BaseEventIsolation, StorageKey


@runtime_checkable
class Coordinator(Protocol):
    @property
    def active_scopes(self) -> int: ...
    def hold(self, key: Hashable) -> AbstractAsyncContextManager[None]: ...
    def scope_token(self, key: Hashable) -> object | None: ...
    def scope_active(self, token: object) -> bool: ...
    def scope_matches(self, key: Hashable, token: object) -> bool: ...


@runtime_checkable
class FencedCoordinator(Coordinator, Protocol):
    def fencing(self, key: Hashable, *, scope: object | None = None) -> tuple[str, str] | None: ...


@runtime_checkable
class LeaseHandle(Protocol):
    @property
    def key(self) -> StorageKey: ...
    @property
    def valid(self) -> bool: ...
    def assert_owned(self) -> None: ...
    async def wait_lost(self) -> None: ...


@runtime_checkable
class IsolationProvider(Protocol):
    @property
    def isolation(self) -> BaseEventIsolation: ...
    def acquire(self, key: StorageKey) -> AbstractAsyncContextManager[LeaseHandle]: ...


@runtime_checkable
class BorrowedFsmCoordinator(Coordinator, Protocol):
    """Structural bridge for acquiring or borrowing the same verified FSM lock.

    Presence of these methods is capability discovery, not proof of ownership;
    installers also validate the configured isolation and live Tracked proof.
    """

    @property
    def fsm_isolation(self) -> BaseEventIsolation | None: ...
    def configure_fsm_isolation(self, isolation: BaseEventIsolation) -> None: ...
    def borrowed_fsm(self, key: Hashable) -> AbstractAsyncContextManager[None]: ...
