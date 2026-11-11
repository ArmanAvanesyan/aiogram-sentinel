"""Renewable Redis conversation locks with task-scoped effect authorization."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import secrets
from collections.abc import AsyncGenerator, Callable, Hashable
from contextlib import asynccontextmanager, suppress
from typing import Protocol, cast

from aiogram.fsm.storage.base import BaseEventIsolation, StorageKey
from aiogram.fsm.storage.memory import SimpleEventIsolation

from .compat import bounded
from .errors import ConfigurationError, OwnershipLost, PersistenceUnavailable
from .identity import coordination_key
from .memory import MemoryCoordinator
from .protocols import LeaseHandle


class _RedisCommands(Protocol):
    async def execute_command(self, *args: object) -> object: ...


# TTL inspection is atomic with the token check. Redis controls expiry itself;
# local monotonic time is only a conservative upper bound on effect authority.
_RENEW = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
if redis.call('PTTL', KEYS[1]) <= 0 then return 0 end
redis.call('PEXPIRE', KEYS[1], ARGV[2])
return redis.call('PTTL', KEYS[1])
"""
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
 return redis.call('DEL', KEYS[1])
end
return 0
"""


class RedisCoordinator(MemoryCoordinator):
    """Serialize protected work across processes using renewable Redis leases.

    Client ownership remains with the caller. Loss of Redis authority revokes
    effect capabilities immediately and cancels the owning task. Applications
    must not swallow cancellation and continue business writes. An already
    running external request cannot be withdrawn by any lease mechanism.
    """

    distributed = True
    configuration_error = ConfigurationError
    ownership_lost_error = OwnershipLost
    persistence_unavailable_error = PersistenceUnavailable

    def __init__(
        self,
        *,
        redis: object,
        prefix: str = "aiogram-coordination",
        lease_seconds: float = 30.0,
        renew_seconds: float = 10.0,
        wait_seconds: float = 30.0,
        poll_seconds: float = 0.05,
        io_timeout: float = 5.0,
    ) -> None:
        super().__init__()
        self._pending_scopes: int = 0
        self._release_scopes = 0
        intervals = (lease_seconds, renew_seconds, wait_seconds, poll_seconds, io_timeout)
        try:
            valid = all(
                not isinstance(v, bool)
                and isinstance(cast(object, v), (int, float))
                and math.isfinite(v)
                and v > 0
                and math.isfinite(v * 1000)
                for v in intervals
            )
        except OverflowError:
            valid = False
        if not valid or lease_seconds * 1000 > 9_223_372_036_854_775_807:
            raise self.configuration_error("Coordinator intervals must be positive bounded numbers")
        if renew_seconds + io_timeout >= lease_seconds:
            raise self.configuration_error("Renewal plus I/O timeout must fit inside the lease")
        if (
            not isinstance(cast(object, prefix), str)
            or not prefix
            or len(prefix) > 256
            or any(character.isspace() for character in prefix)
        ):
            raise self.configuration_error("Redis prefix must be bounded and contain no whitespace")
        self._redis = cast(_RedisCommands, redis)
        self.prefix = prefix
        self.lease_seconds = lease_seconds
        self.renew_seconds = renew_seconds
        self.wait_seconds = wait_seconds
        self.poll_seconds = poll_seconds
        self.io_timeout = io_timeout
        self._lease_ms = max(1, math.ceil(lease_seconds * 1000))
        self._valid_until: dict[object, float] = {}
        self._fences: dict[object, tuple[str, str]] = {}
        self._scope_events: dict[object, asyncio.Event] = {}
        self._fsm_proofs: dict[object, LeaseHandle] = {}
        self.fsm_isolation: BaseEventIsolation | None = None

    @property
    def active_scopes(self) -> int:
        # Revocation removes effect authority, not the task that still owns the
        # protected handler. Keep shutdown/configuration blocked until cleanup.
        from .isolation import TrackedEventIsolation

        fsm_active = (
            self.fsm_isolation.active_scopes
            if isinstance(self.fsm_isolation, TrackedEventIsolation)
            else 0
        )
        return max(len(self._fences) + self._pending_scopes + self._release_scopes, fsm_active)

    def configure_fsm_isolation(self, isolation: BaseEventIsolation) -> None:
        """Share the exact local FSM lock with workers, before protected work."""
        from .isolation import TrackedEventIsolation

        if type(isolation) is not SimpleEventIsolation and not isinstance(
            isolation, TrackedEventIsolation
        ):
            raise self.configuration_error(
                "Only verified Simple or TrackedEventIsolation is supported"
            )
        if self.fsm_isolation is isolation:
            return
        if self.fsm_isolation is not None or self.active_scopes or self._fences:
            raise self.configuration_error(
                "Redis FSM isolation cannot change after binding or during work"
            )
        self.fsm_isolation = isolation

    @asynccontextmanager
    async def borrowed_fsm(self, key: Hashable) -> AsyncGenerator[None, None]:
        """Use only when dispatcher middleware already holds the verified FSM lock."""
        if self.fsm_isolation is None:
            raise self.configuration_error("No verified FSM isolation is configured")
        from .isolation import TrackedEventIsolation

        if isinstance(self.fsm_isolation, TrackedEventIsolation):
            normalized = coordination_key(key)
            storage_key = StorageKey(
                bot_id=normalized.bot_id, chat_id=normalized.chat_id, user_id=normalized.user_id
            )
            async with self.fsm_isolation.borrowed(storage_key), self._hold_redis(key):
                yield
        else:
            async with self._hold_redis(key):
                yield

    @asynccontextmanager
    async def hold(self, key: Hashable) -> AsyncGenerator[None, None]:
        key = self.normalize_key(key)
        coordination_key(key)
        self._check_reentry(key)
        if self.fsm_isolation is not None and not self.owns(key):
            normalized = coordination_key(key)
            storage_key = StorageKey(
                bot_id=normalized.bot_id, chat_id=normalized.chat_id, user_id=normalized.user_id
            )
            self._pending_scopes += 1
            acquired = False
            try:
                async with self.fsm_isolation.lock(key=storage_key):
                    self._pending_scopes -= 1
                    acquired = True
                    async with self._hold_redis(key):
                        yield
            finally:
                if not acquired:
                    self._pending_scopes -= 1
        else:
            async with self._hold_redis(key):
                yield

    def _check_reentry(self, key: Hashable) -> None:
        key = self.normalize_key(key)
        task = asyncio.current_task()
        if not self.owns(key) and any(
            held == key and owner is task for held, owner, _ in self._scope_tokens.get()
        ):
            raise self.ownership_lost_error(
                "A revoked conversation scope cannot acquire new ownership"
            )

    def lock_key(self, key: Hashable) -> str:
        """Canonical full-identity lock key, without disclosing tenant names."""
        normalized = coordination_key(key)
        identity = [
            normalized.namespace,
            normalized.tenant_id,
            normalized.bot_id,
            normalized.chat_id,
            normalized.user_id,
        ]
        digest = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
        return f"{self.prefix}:conversation-lock:{digest}"

    def scope_active(self, token: object) -> bool:
        deadline = self._valid_until.get(token)
        proof = self._fsm_proofs.get(token)
        if (deadline is not None and asyncio.get_running_loop().time() >= deadline) or (
            proof is not None and not proof.valid
        ):
            self._live_scopes.discard(token)
            event = self._scope_events.get(token)
            if event is not None:
                event.set()
        return super().scope_active(token)

    async def wait_scope_lost(self, token: object) -> None:
        event = self._scope_events.get(token)
        if event is None or not self.scope_active(token):
            return
        await event.wait()

    def scope_token(self, key: Hashable) -> object | None:
        token = super().scope_token(key)
        return token if token is not None and self.scope_active(token) else None

    def fencing(self, key: Hashable, *, scope: object | None = None) -> tuple[str, str] | None:
        """Return the actual task's live lock key/token for atomic Redis writes.

        A local scope check alone cannot fence a mutation: the backend must
        compare this token and positive PTTL inside its commit Lua script.
        """
        if scope is not None:
            fence = self._fences.get(scope)
            if not self.scope_active(scope) or fence is None or fence[0] != self.lock_key(key):
                raise self.ownership_lost_error(
                    "Effect scope is expired or belongs to another conversation"
                )
            return fence
        self._check_reentry(key)
        current = self.scope_token(key)
        return self._fences.get(current) if current is not None else None

    async def _command(self, *args: object) -> object:
        try:
            async with bounded(self.io_timeout):
                return await self._redis.execute_command(*args)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise self.persistence_unavailable_error(
                "Redis conversation coordination unavailable"
            ) from exc

    async def _renew(
        self, lock: str, owner: str, scope: object, cancel_owner: Callable[[], None]
    ) -> None:
        try:
            while True:
                await asyncio.sleep(self.renew_seconds)
                started = asyncio.get_running_loop().time()
                ttl = await self._command("EVAL", _RENEW, 1, lock, owner, self._lease_ms)
                if not isinstance(ttl, int) or ttl <= 0:
                    raise self.ownership_lost_error("Redis conversation lease lost")
                self._valid_until[scope] = started + ttl / 1000
        except asyncio.CancelledError:
            raise
        except Exception:
            self._live_scopes.discard(scope)
            event = self._scope_events.get(scope)
            if event is not None:
                event.set()
            cancel_owner()

    @asynccontextmanager
    async def _hold_redis(self, key: Hashable) -> AsyncGenerator[None, None]:
        key = self.normalize_key(key)
        coordination_key(key)
        self._check_reentry(key)
        if self.owns(key):
            yield
            return
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Conversation coordination requires an asyncio task")
        from .isolation import TrackedEventIsolation

        fsm_proof: LeaseHandle | None = None
        if isinstance(self.fsm_isolation, TrackedEventIsolation):
            normalized = coordination_key(key)
            storage_key = StorageKey(
                bot_id=normalized.bot_id, chat_id=normalized.chat_id, user_id=normalized.user_id
            )
            fsm_proof = self.fsm_isolation.proof(storage_key)
        lock, owner = self.lock_key(key), secrets.token_hex(24)
        acquired = False
        cleanup_counted = False
        self._pending_scopes += 1
        started = asyncio.get_running_loop().time()
        try:
            try:
                async with bounded(self.wait_seconds):
                    while True:
                        started = asyncio.get_running_loop().time()
                        if await self._command("SET", lock, owner, "NX", "PX", self._lease_ms):
                            acquired = True
                            break
                        await asyncio.sleep(self.poll_seconds)
            except asyncio.TimeoutError as exc:
                raise self.ownership_lost_error(
                    "Timed out waiting for Redis conversation lock"
                ) from exc
            self._pending_scopes -= 1
            async with self._scope(key):
                scope = super().scope_token(key)
                # Scope is allocated by _scope().
                assert scope is not None  # nosec B101
                self._valid_until[scope] = started + self.lease_seconds
                self._fences[scope] = (lock, owner)
                self._scope_events[scope] = asyncio.Event()
                if fsm_proof is not None:
                    self._fsm_proofs[scope] = fsm_proof
                cancelling = cast(Callable[[], int] | None, getattr(task, "cancelling", None))
                uncancel = cast(Callable[[], int] | None, getattr(task, "uncancel", None))
                baseline = cancelling() if cancelling is not None else 0
                marker = object()
                requested = consumed = legacy_marker = False
                legacy_previous: object = None

                def cancel_owner() -> None:
                    nonlocal requested, legacy_marker, legacy_previous
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

                renewer = asyncio.create_task(self._renew(lock, owner, scope, cancel_owner))
                try:
                    if not self.scope_active(scope):
                        raise self.ownership_lost_error(
                            "Redis conversation lease expired during acquisition"
                        )
                    yield
                    if not self.scope_active(scope):
                        raise self.ownership_lost_error("Redis conversation lease lost")
                except asyncio.CancelledError as exc:
                    remaining = consume()
                    owned_cancel = requested and (
                        remaining <= baseline
                        if cancelling is not None
                        else exc.args == (marker,)
                        and (not legacy_marker or getattr(task, "_cancel_message", None) is marker)
                    )
                    if owned_cancel:
                        raise self.ownership_lost_error("Redis conversation lease lost") from exc
                    raise
                finally:
                    self._release_scopes += 1
                    cleanup_counted = True
                    self._live_scopes.discard(scope)
                    event = self._scope_events.pop(scope, None)
                    if event is not None:
                        event.set()
                    self._valid_until.pop(scope, None)
                    self._fences.pop(scope, None)
                    self._fsm_proofs.pop(scope, None)
                    if legacy_marker and getattr(task, "_cancel_message", None) is marker:
                        setattr(task, "_cancel_message", legacy_previous)  # noqa: B010
                    consume()
                    renewer.cancel()
                    # return_exceptions absorbs the child cancellation only. An
                    # external cancellation of the owner during cleanup propagates.
                    await asyncio.gather(renewer, return_exceptions=True)
        finally:
            if not cleanup_counted:
                self._release_scopes += 1
            try:
                if not acquired:
                    self._pending_scopes -= 1
                # Count release until token-checked Redis cleanup ends, even when
                # SET/release responses are ambiguous or cancellation interrupts.
                with suppress(self.persistence_unavailable_error):
                    await self._command("EVAL", _RELEASE, 1, lock, owner)
            finally:
                self._release_scopes -= 1
