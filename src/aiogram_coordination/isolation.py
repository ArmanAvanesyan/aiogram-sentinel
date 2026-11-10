"""Explicit, verifiable application-owned FSM isolation integration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Hashable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import cast

from aiogram.fsm.storage.base import BaseEventIsolation, StorageKey
from aiogram.fsm.storage.memory import SimpleEventIsolation

from .errors import ConfigurationError, OwnershipLost
from .identity import coordination_key
from .memory import MemoryCoordinator
from .protocols import IsolationProvider, LeaseHandle


@dataclass
class _MemoryLease:
    key: StorageKey
    lost: asyncio.Event

    @property
    def valid(self) -> bool:
        return not self.lost.is_set()

    def assert_owned(self) -> None:
        if not self.valid:
            raise OwnershipLost("FSM isolation ownership ended")

    async def wait_lost(self) -> None:
        await self.lost.wait()


class _SimpleProvider:
    def __init__(self, isolation: SimpleEventIsolation) -> None:
        self.isolation = isolation

    @asynccontextmanager
    async def acquire(self, key: StorageKey) -> AsyncGenerator[LeaseHandle, None]:
        async with self.isolation.lock(key=key):
            lease = _MemoryLease(key, asyncio.Event())
            try:
                yield lease
            finally:
                lease.lost.set()


@dataclass
class _Held:
    key: StorageKey
    task: asyncio.Task[object]
    lease: LeaseHandle
    revoked: bool = False

    @property
    def valid(self) -> bool:
        return not self.revoked and self.lease.valid

    def assert_owned(self) -> None:
        if not self.valid:
            raise OwnershipLost("Captured FSM scope was revoked")

    async def wait_lost(self) -> None:
        if not self.valid:
            return
        await self.lease.wait_lost()


class TrackedEventIsolation(BaseEventIsolation):
    """Wrap application isolation at Dispatcher construction, never at install.

    Only SimpleEventIsolation has a safe implicit provider. A custom provider
    must explicitly reference the same underlying isolation and return a live,
    key-bound lease; opaque fixed-TTL locks are never assumed to renew.
    """

    def __init__(
        self,
        isolation: BaseEventIsolation,
        *,
        provider: IsolationProvider | None = None,
        close_delegate: bool = False,
    ) -> None:
        if not isinstance(cast(object, isolation), BaseEventIsolation):
            raise ConfigurationError("Expected an application BaseEventIsolation")
        if provider is None:
            if type(isolation) is SimpleEventIsolation:
                provider = _SimpleProvider(isolation)
            elif isinstance(isolation, RenewableRedisEventIsolation):
                provider = isolation
            else:
                raise ConfigurationError("Custom isolation requires an explicit lease provider")
        if (
            not isinstance(cast(object, provider), IsolationProvider)
            or provider.isolation is not isolation
        ):
            raise ConfigurationError("Lease provider must describe the exact application isolation")
        if type(close_delegate) is not bool:
            raise ConfigurationError("close_delegate must be boolean")
        self.isolation = isolation
        self.provider = provider
        self.close_delegate = close_delegate
        self._owned: ContextVar[tuple[_Held, ...]] = ContextVar(
            f"tracked_fsm_{id(self)}", default=()
        )
        self._pending = 0
        self._closed = False

    @property
    def active_scopes(self) -> int:
        return self._pending

    def _held(self, key: StorageKey) -> _Held | None:
        task = asyncio.current_task()
        return next(
            (held for held in reversed(self._owned.get()) if held.key == key and held.task is task),
            None,
        )

    def owns(self, key: StorageKey) -> bool:
        held = self._held(key)
        return held is not None and not held.revoked and held.lease.valid

    def proof(self, key: StorageKey) -> LeaseHandle:
        held = self._held(key)
        if held is None:
            raise OwnershipLost("FSM scope is not owned by this task")
        held.assert_owned()
        return held

    @asynccontextmanager
    async def borrowed(self, key: StorageKey) -> AsyncGenerator[None, None]:
        held = self._held(key)
        if held is None or held.revoked:
            raise OwnershipLost("FSM lock is not owned by this task")
        held.lease.assert_owned()
        yield
        if held.revoked or not held.lease.valid:
            raise OwnershipLost("Borrowed FSM scope was revoked")

    @asynccontextmanager
    async def _acquire(self, key: StorageKey) -> AsyncGenerator[LeaseHandle, None]:
        self._pending += 1
        try:
            async with self.provider.acquire(key) as lease:
                if self._closed:
                    raise ConfigurationError("FSM isolation closed during acquisition")
                yield lease
        finally:
            # Includes waiting, protected work AND provider.__aexit__ release.
            self._pending -= 1

    @asynccontextmanager
    async def lock(self, key: StorageKey) -> AsyncGenerator[None, None]:
        if self._closed or not isinstance(cast(object, key), StorageKey):
            raise ConfigurationError("Isolation is closed or the FSM key is invalid")
        if self._held(key) is not None:
            async with self.borrowed(key):
                yield
            return
        task = asyncio.current_task()
        if task is None:
            raise ConfigurationError("FSM coordination requires a task")
        async with self._acquire(key) as lease:
            if not isinstance(cast(object, lease), LeaseHandle) or lease.key != key:
                raise ConfigurationError("Isolation provider returned an invalid lease identity")
            lease.assert_owned()
            held = _Held(key, task, lease)
            token = self._owned.set((*self._owned.get(), held))
            marker = object()
            cancelling = cast(Callable[[], int] | None, getattr(task, "cancelling", None))
            uncancel = cast(Callable[[], int] | None, getattr(task, "uncancel", None))
            baseline = cancelling() if cancelling is not None else 0
            requested = consumed = legacy_marker = False
            legacy_previous: object = None

            async def watch() -> None:
                nonlocal requested, legacy_marker, legacy_previous
                try:
                    await lease.wait_lost()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # An inability to monitor ownership must revoke permission.
                    pass
                held.revoked = True
                if cancelling is None:
                    legacy_previous = getattr(task, "_cancel_message", None)
                requested = task.cancel(marker)
                if requested and cancelling is None and hasattr(task, "_cancel_message"):
                    try:
                        setattr(task, "_cancel_message", marker)  # noqa: B010 -- CPython 3.10
                    except (AttributeError, TypeError):
                        pass
                    else:
                        legacy_marker = True

            def consume() -> int:
                nonlocal consumed
                if requested and not consumed and uncancel is not None:
                    consumed = True
                    return uncancel()
                return cancelling() if cancelling is not None else 0

            watcher = asyncio.create_task(watch())
            try:
                yield
                if held.revoked or not lease.valid:
                    raise OwnershipLost("FSM isolation lease lost")
            except asyncio.CancelledError as error:
                remaining = consume()
                if requested and (
                    remaining <= baseline
                    if cancelling is not None
                    else error.args == (marker,)
                    and (not legacy_marker or getattr(task, "_cancel_message", None) is marker)
                ):
                    raise OwnershipLost("FSM isolation lease lost") from error
                raise
            finally:
                held.revoked = True
                self._owned.reset(token)
                if legacy_marker and getattr(task, "_cancel_message", None) is marker:
                    setattr(task, "_cancel_message", legacy_previous)  # noqa: B010
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
                consume()

    async def close(self) -> None:
        if self.active_scopes:
            raise ConfigurationError("Drain FSM scopes before closing isolation")
        self._closed = True
        if self.close_delegate:
            await self.isolation.close()


class AiogramMemoryCoordinator(MemoryCoordinator):
    """Borrow a proven FSM scope; workers acquire the same normalized lock."""

    configuration_error = ConfigurationError
    ownership_lost_error = OwnershipLost

    def __init__(self, isolation: object) -> None:
        if type(isolation) is not SimpleEventIsolation and not isinstance(
            isolation, TrackedEventIsolation
        ):
            raise self.configuration_error("Expected verified Simple or TrackedEventIsolation")
        super().__init__()
        self.isolation = isolation
        self._fsm_proofs: dict[object, LeaseHandle] = {}

    @property
    def active_scopes(self) -> int:
        fsm_active = (
            self.isolation.active_scopes if isinstance(self.isolation, TrackedEventIsolation) else 0
        )
        return max(super().active_scopes, fsm_active)

    @property
    def fsm_isolation(self) -> BaseEventIsolation:
        return self.isolation

    def configure_fsm_isolation(self, isolation: BaseEventIsolation) -> None:
        if isolation is not self.isolation:
            raise self.configuration_error("FSM bridge cannot replace its configured isolation")

    def borrowed_fsm(self, key: Hashable) -> AbstractAsyncContextManager[None]:
        return self.borrowed(key)

    def scope_active(self, token: object) -> bool:
        proof = self._fsm_proofs.get(token)
        if proof is not None and not proof.valid:
            self._live_scopes.discard(token)
        return super().scope_active(token)

    @asynccontextmanager
    async def borrowed(self, key: Hashable) -> AsyncGenerator[None, None]:
        key = self.normalize_key(key)
        normalized = coordination_key(key)
        fsm_key = StorageKey(
            bot_id=normalized.bot_id, chat_id=normalized.chat_id, user_id=normalized.user_id
        )
        if self.owns(key):
            yield
            return
        if isinstance(self.isolation, TrackedEventIsolation):
            proof = self.isolation.proof(fsm_key)
            async with self.isolation.borrowed(fsm_key), self._scope(key):
                scope = self.scope_token(key)
                if scope is None:
                    raise self.ownership_lost_error("No borrowed FSM scope was established")
                self._fsm_proofs[scope] = proof
                try:
                    yield
                finally:
                    self._fsm_proofs.pop(scope, None)
        else:
            # Legacy installer verifies this branch executes inside aiogram FSM.
            async with self._scope(key):
                yield

    @asynccontextmanager
    async def hold(self, key: Hashable) -> AsyncGenerator[None, None]:
        key = self.normalize_key(key)
        self._check_reentry(key)
        if self.owns(key):
            yield
            return
        normalized = coordination_key(key)
        fsm_key = StorageKey(
            bot_id=normalized.bot_id, chat_id=normalized.chat_id, user_id=normalized.user_id
        )
        self._pending_scopes += 1
        acquired = False
        try:
            async with self.isolation.lock(key=fsm_key):
                self._pending_scopes -= 1
                acquired = True
                async with self.borrowed(key):
                    yield
        finally:
            if not acquired:
                self._pending_scopes -= 1


# Imported last to keep Redis coordination independent of this adapter module.
from .redis_isolation import RenewableRedisEventIsolation  # noqa: E402
