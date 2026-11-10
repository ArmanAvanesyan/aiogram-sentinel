"""Authoritative server-time envelopes with bounded atomic CAS retries."""

from __future__ import annotations

# The memory backend is intentionally used only as an ephemeral pure reducer.
# pyright: reportPrivateUsage=false
import asyncio
import hashlib
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace
from typing import TypeVar, cast

from ..clock import ManualClock
from ..codec import decode, encode
from ..config import NavigationConfig
from ..errors import (
    ConfigurationError,
    Overloaded,
    OwnershipLost,
    PersistenceUnavailable,
    SessionExpired,
    VersionConflict,
)
from ..models import ConversationKey, NavigationToken, PreparedAction
from .deployment import RedisDeploymentAttestation, validate_deployment
from .memory import MemoryNavigationRepository
from .redis_codec import dumps, loads
from .redis_coordinator import RedisCoordinator
from .redis_scripts import COMMIT, INITIALIZE, READ, SCAN_PAGE
from .redis_transport import Connection, RedisClock, array, text
from .tokens import _known_tokens

T = TypeVar("T")


class RedisStore:
    def __init__(
        self,
        redis: object,
        prefix: str,
        config: NavigationConfig,
        deployment: RedisDeploymentAttestation | None = None,
    ) -> None:
        if (
            not isinstance(cast(object, prefix), str)
            or not prefix
            or len(prefix) > 200
            or any(c.isspace() for c in prefix)
        ):
            raise ConfigurationError("Redis prefix must be bounded and contain no whitespace")
        if deployment is not None and not isinstance(
            cast(object, deployment), RedisDeploymentAttestation
        ):
            raise ConfigurationError("Expected explicit Redis deployment attestation")
        self.deployment = deployment
        self.storage_format = 1
        self.prefix, self.config = prefix, config
        self.clock = RedisClock()
        self.connection = Connection(redis, self.clock)
        self.coordinator = RedisCoordinator(redis=redis, prefix=prefix)
        profile = asdict(config)
        profile.pop("root")
        profile.pop("engine")
        profile["session_seconds"] = float(config.session_seconds)
        profile["recovery_seconds"] = float(config.recovery_seconds)
        self.profile = encode(profile)
        self.base_profile = self.profile
        self.history = ""
        self.initialized = False
        self.cursor = "0"
        self.backlog: list[str] = []
        self._sweep_lock = asyncio.Lock()

    @property
    def base_keys(self) -> list[str]:
        return [f"{self.prefix}:profile", f"{self.prefix}:established"]

    def member(self, key: ConversationKey) -> str:
        return encode(key)

    def keys(self, key: ConversationKey) -> list[str]:
        ident = hashlib.sha256(self.member(key).encode()).hexdigest()
        return [*self.base_keys, f"{self.prefix}:record:{ident}", f"{self.prefix}:live"]

    async def initialize(self) -> None:
        if self.initialized:
            return
        from .redis_migration import initialize_format

        await validate_deployment(self.connection, self.deployment)
        await initialize_format(self)
        marker = text(
            await self.connection.script(
                INITIALIZE,
                [*self.base_keys, f"{self.prefix}:live"],
                [self.profile, secrets.token_urlsafe(18)],
            )
        )
        if marker == "profile":
            raise ConfigurationError(
                "Redis navigation replicas require the same storage configuration"
            )
        if marker == "history":
            raise PersistenceUnavailable(
                "Redis namespace history is incomplete; explicit recovery required"
            )
        self.history = marker
        await self.connection.time()
        self.initialized = True

    async def read(self, key: ConversationKey) -> tuple[str, MemoryNavigationRepository]:
        await self.initialize()
        values = array(
            await self.connection.script(
                READ, self.keys(key), [self.profile, self.history, self.member(key)], mutation=False
            )
        )
        if text(values[0]) != "ok":
            raise PersistenceUnavailable("Redis navigation history or index was lost")
        now = int(text(values[2])) * 1000 + int(text(values[3])) // 1000
        self.clock.update(now)
        memory = MemoryNavigationRepository(clock=ManualClock(now), config=self.config)
        memory._storage_format = self.storage_format
        raw = text(values[1])
        if raw:
            memory._records[key] = loads(raw, key, engine=self.config.engine)
        return raw, memory

    async def apply(
        self,
        key: ConversationKey,
        callback: Callable[[MemoryNavigationRepository], Awaitable[T]],
        *,
        scope: object | None = None,
        deadline: Callable[[T], int] | None = None,
        prune: bool = False,
    ) -> T:
        for _ in range(16):
            raw, memory = await self.read(key)
            if scope is not None and not self.coordinator.scope_matches(key, scope):
                raise OwnershipLost("Navigation coordination capability expired")
            original = memory._records.get(key)
            previous_actions = (
                {name: entry.prepared for name, entry in original.operations.items()}
                if original is not None and deadline is not None
                else {}
            )
            previous_tokens = (
                {entry.token.token: replace(entry) for entry in _known_tokens(original)}
                if original is not None and deadline is not None
                else {}
            )
            result = await callback(memory)
            record = memory._records.get(key)
            if prune and record is not None and memory._removable(record):
                del memory._records[key]
                record = None
            try:
                updated = (
                    dumps(key, record, storage_format=self.storage_format)
                    if record is not None
                    else ""
                )
            except ConfigurationError as error:
                raise Overloaded("Redis navigation envelope exceeds supported limits") from error
            expires = deadline(result) if deadline is not None and updated != raw else 0
            if isinstance(result, PreparedAction):
                if previous_actions.get(result.operation_id) == result:
                    expires = 0
            if record is not None and isinstance(result, NavigationToken):
                old = previous_tokens.get(result.token)
                old_tokens = [old] if old is not None else []
                new_tokens = [
                    item for item in _known_tokens(record) if item.token.token == result.token
                ]
                if old_tokens and old_tokens == new_tokens:
                    expires = 0
            # Even idempotent retries must validate a supplied live scope atomically.
            fence = self.coordinator.fencing(key, scope=scope)
            keys = self.keys(key)
            keys.append(fence[0] if fence else f"{self.prefix}:unused-lock")
            status = text(
                await self.connection.script(
                    COMMIT,
                    keys,
                    [
                        self.profile,
                        self.history,
                        self.member(key),
                        raw,
                        updated,
                        self.config.max_conversations,
                        fence[1] if fence else "",
                        expires,
                    ],
                )
            )
            if status == "ok":
                return result
            if status == "retry":
                continue
            if status == "capacity":
                raise Overloaded("Retained navigation conversation capacity exhausted; sweep first")
            if status == "ownership":
                raise OwnershipLost("Redis navigation coordination lease expired")
            if status == "expired":
                raise SessionExpired("Navigation authorization expired before Redis commit")
            raise PersistenceUnavailable("Redis navigation namespace history is inconsistent")
        raise VersionConflict("Redis navigation CAS contention limit reached")

    async def sweep(self, limit: int) -> int:
        if type(limit) is not int or limit <= 0:
            raise ValueError("Sweep limit must be a positive integer")
        async with self._sweep_lock:
            return await self._sweep(limit)

    async def _sweep(self, limit: int) -> int:
        await self.initialize()
        # Validate namespace history even with buffered work or an empty index.
        response = array(
            await self.connection.script(
                SCAN_PAGE,
                [*self.base_keys, f"{self.prefix}:live"],
                [self.profile, self.history, self.cursor, min(limit, 100)],
                mutation=False,
            )
        )
        if text(response[0]) != "ok":
            raise PersistenceUnavailable("Redis navigation history or index was lost")
        if not self.backlog:
            self.cursor = str(response[1]) if type(response[1]) is int else text(response[1])
            if not self.cursor.isdecimal():
                raise PersistenceUnavailable("Redis scan cursor is malformed")
            self.backlog.extend(text(value) for value in array(response[2]))
        selected, self.backlog = self.backlog[:limit], self.backlog[limit:]
        removed = 0
        for member in selected:
            if member == "!established":
                continue
            try:
                key = decode(member)
            except ConfigurationError as error:
                raise PersistenceUnavailable(
                    "Redis navigation index identity is invalid"
                ) from error
            if not isinstance(key, ConversationKey):
                raise PersistenceUnavailable("Redis navigation index identity is invalid")

            async def prune(memory: MemoryNavigationRepository, key: ConversationKey = key) -> bool:
                record = memory._records.get(key)
                return record is not None and memory._removable(record)

            removed += int(await self.apply(key, prune, prune=True))
        return removed
