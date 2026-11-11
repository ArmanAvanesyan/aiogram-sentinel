"""Single-process, task-scoped conversation coordination."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Hashable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from .errors import OwnershipLost
from .identity import coordination_key


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


class MemoryCoordinator:
    """Serialize a whole handler and worker for each conversation.

    Ownership is checked against the actual asyncio Task. Context copied into a
    child task never grants that task permission to bypass the lock.
    """

    ownership_lost_error = OwnershipLost

    def __init__(self) -> None:
        self._locks: dict[Hashable, _LockEntry] = {}
        self._owned: ContextVar[tuple[tuple[Hashable, asyncio.Task[object]], ...]] = ContextVar(
            f"coord_owned_{id(self)}", default=()
        )

        self._scope_tokens: ContextVar[
            tuple[tuple[Hashable, asyncio.Task[object], object], ...]
        ] = ContextVar(f"coord_scope_tokens_{id(self)}", default=())
        self._live_scopes: set[object] = set()
        self._scope_keys: dict[object, Hashable] = {}
        self._pending_scopes = 0

    def normalize_key(self, key: Hashable) -> Hashable:
        if all(
            hasattr(key, field)
            for field in ("namespace", "tenant_id", "bot_id", "chat_id", "user_id")
        ):
            return coordination_key(key)
        return key

    @property
    def active_scopes(self) -> int:
        return len(self._scope_keys) + self._pending_scopes

    def scope_token(self, key: Hashable) -> object | None:
        key = self.normalize_key(key)
        task = asyncio.current_task()
        for held, owner, token in reversed(self._scope_tokens.get()):
            if held == key and owner is task and self.scope_active(token):
                return token
        return None

    def scope_active(self, token: object) -> bool:
        return token in self._live_scopes

    def scope_matches(self, key: Hashable, token: object) -> bool:
        """Validate a delegated capability without granting task lock ownership."""
        return self._scope_keys.get(token) == self.normalize_key(key) and self.scope_active(token)

    @asynccontextmanager
    async def _scope(self, key: Hashable) -> AsyncGenerator[None, None]:
        key = self.normalize_key(key)
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Conversation coordination requires an asyncio task")
        scope = object()
        self._live_scopes.add(scope)
        self._scope_keys[scope] = key
        ownership = self._owned.set((*self._owned.get(), (key, task)))
        tokens = self._scope_tokens.set((*self._scope_tokens.get(), (key, task, scope)))
        try:
            yield
        finally:
            self._live_scopes.discard(scope)
            self._scope_keys.pop(scope, None)
            self._scope_tokens.reset(tokens)
            self._owned.reset(ownership)

    def owns(self, key: Hashable) -> bool:
        return self.scope_token(key) is not None

    def _check_reentry(self, key: Hashable) -> None:
        key = self.normalize_key(key)
        task = asyncio.current_task()
        if not self.owns(key) and any(
            held == key and owner is task for held, owner, _ in self._scope_tokens.get()
        ):
            raise self.ownership_lost_error("A revoked scope cannot acquire fresh ownership")

    @asynccontextmanager
    async def hold(self, key: Hashable) -> AsyncGenerator[None, None]:
        key = self.normalize_key(key)
        self._check_reentry(key)
        if self.owns(key):
            yield
            return
        entry = self._locks.setdefault(key, _LockEntry(asyncio.Lock()))
        entry.users += 1
        self._pending_scopes += 1
        acquired = False
        try:
            async with entry.lock:
                self._pending_scopes -= 1
                acquired = True
                async with self._scope(key):
                    yield
        finally:
            if not acquired:
                self._pending_scopes -= 1
            entry.users -= 1
            if entry.users == 0:
                self._locks.pop(key, None)

    @property
    def lock_count(self) -> int:
        """Number of active or contended locks, useful for health checks."""
        return len(self._locks)
