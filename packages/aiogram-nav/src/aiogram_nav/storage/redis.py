"""Standalone Redis navigation repository; install the optional Redis extra."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, Protocol, TypeVar, cast

from aiogram_coordination import ExternalSession

from ..clock import Clock
from ..config import NavigationConfig
from ..engine import EngineName
from ..errors import ConfigurationError, Overloaded
from ..models import (
    ActionStatus,
    CommitResult,
    ConversationKey,
    EffectCheckpoint,
    NavigationIntent,
    NavigationMutation,
    NavigationToken,
    PreparedAction,
    RenderResult,
    VersionedSnapshot,
)
from ..protocols import Coordinator
from .deployment import RedisDeploymentAttestation
from .memory import MemoryNavigationRepository
from .redis_store import RedisStore
from .sessions import StorageMigrationReport

T = TypeVar("T")


class RedisNavigationRepository:
    """Authoritative standalone Redis 7+ storage with fenced conversation leases.

    A caller-supplied client remains caller-owned. ``from_url`` creates an owned
    client. No in-process copy survives a repository operation. Redis must use
    noeviction; persistence/replication durability remains a deployment choice.
    """

    capabilities = frozenset(
        {"conditional_commits", "prepared_actions", "opaque_tokens", "distributed", "durable"}
    )

    def __init__(
        self,
        *,
        redis: object,
        prefix: str = "aiogram-nav",
        config: NavigationConfig | None = None,
        engine: EngineName | None = None,
        storage_format: int | None = None,
        deployment: RedisDeploymentAttestation | None = None,
    ) -> None:
        self.prefix = prefix
        self.config = config or NavigationConfig()
        if engine is not None:
            self.config = replace(self.config, engine=engine)
        self._store = RedisStore(
            redis, prefix, self.config, deployment, storage_format=storage_format
        )
        self.clock: Clock = self._store.clock
        self.coordinator: Coordinator = self._store.coordinator
        self._owned_client: object | None = None

    @classmethod
    async def from_url(
        cls,
        url: str,
        *,
        prefix: str = "aiogram-nav",
        config: NavigationConfig | None = None,
        engine: EngineName | None = None,
        storage_format: int | None = None,
        deployment: RedisDeploymentAttestation | None = None,
    ) -> RedisNavigationRepository:
        if storage_format is not None and (
            type(storage_format) is not int or storage_format not in (1, 3)
        ):
            raise ConfigurationError("Fresh storage_format must be 1 or 3")
        effective = config or NavigationConfig()
        if engine is not None:
            effective = replace(effective, engine=engine)
        try:
            from redis.asyncio import Redis
        except ImportError as error:
            raise ConfigurationError("Install aiogram-nav[redis] to use from_url") from error
        client = cast(Any, Redis).from_url(url, socket_timeout=5, socket_connect_timeout=5)
        repository = cls(
            redis=client,
            prefix=prefix,
            config=effective,
            deployment=deployment,
            storage_format=storage_format,
        )
        repository._owned_client = client
        try:
            await repository.initialize()
        except BaseException:
            await client.aclose()
            raise
        return repository

    async def initialize(self) -> None:
        await self._store.initialize()

    @property
    def storage_format(self) -> int:
        """Established format; call initialize before inspecting a new instance."""
        return self._store.storage_format

    @property
    def atomic_adoption(self) -> bool:
        return type(self) is RedisNavigationRepository and (
            self.storage_format == 3 or self._store.requested_storage_format == 3
        )

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
        from .redis_migration import activate_storage_format

        return await activate_storage_format(
            self._store,
            expected=expected,
            target=target,
            operation_id=operation_id,
            old_workers_drained=old_workers_drained,
            dry_run=dry_run,
        )

    async def migrate_storage_page(
        self, *, cursor: str = "0:0", limit: int = 100
    ) -> dict[str, object]:
        """Bounded explicit eager conversion; activation and effects remain separate."""
        from .redis_migration import migrate_page

        return await migrate_page(self._store, cursor=cursor, limit=limit)

    async def external_session(self, key: ConversationKey) -> ExternalSession | None:
        _, memory = await self._store.read(key)
        return await memory.external_session(key)

    async def bind_external_session(
        self,
        key: ConversationKey,
        session: ExternalSession,
        *,
        coordination_scope: object | None = None,
    ) -> None:
        await self.initialize()
        self.require_storage_format(2)
        await self._apply(
            key,
            lambda memory: memory.bind_external_session(key, session),
            scope=coordination_scope,
            deadline=lambda _: session.expires_at,
        )

    def bind_coordinator(self, coordinator: Coordinator) -> None:
        if coordinator is not self.coordinator:
            raise ConfigurationError("Redis navigation requires its shared distributed coordinator")

    async def _apply(
        self,
        key: ConversationKey,
        callback: Callable[[MemoryNavigationRepository], Awaitable[T]],
        *,
        scope: object | None = None,
        deadline: Callable[[T], int] | None = None,
        operation_id: str = "",
        token: str = "",
        reservation_id: str = "",
        view_id: str = "",
    ) -> T:
        try:
            return await self._store.apply(
                key,
                callback,
                scope=scope,
                deadline=deadline,
                operation_id=operation_id,
                token=token,
                reservation_id=reservation_id,
                view_id=view_id,
            )
        except Overloaded:
            # Bounded reclamation only; unresolved evidence is never evicted.
            await self.sweep(limit=100)
            return await self._store.apply(
                key,
                callback,
                scope=scope,
                deadline=deadline,
                operation_id=operation_id,
                token=token,
                reservation_id=reservation_id,
                view_id=view_id,
            )

    async def load(self, key: ConversationKey) -> VersionedSnapshot | None:
        _, memory = await self._store.read(key)
        return await memory.load(key)

    async def prepare(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        intent: NavigationIntent,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
        return await self._apply(
            key,
            lambda memory: memory.prepare(key, expected_version=expected_version, intent=intent),
            scope=coordination_scope,
            deadline=lambda result: result.expires_at,
            operation_id=intent.operation_id,
            view_id=intent.view_id or "" if intent.action == "track" else "",
        )

    async def adopt_render(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        intent: NavigationIntent,
        rendered: RenderResult,
        coordination_scope: object | None = None,
    ) -> CommitResult:
        return await self._apply(
            key,
            lambda memory: memory.adopt_render(
                key, expected_version=expected_version, intent=intent, rendered=rendered
            ),
            scope=coordination_scope,
            deadline=lambda result: 0 if result.duplicate else result.snapshot.expires_at,
            operation_id=intent.operation_id,
            view_id=intent.view_id or "" if intent.action == "track" else "",
        )

    async def checkpoint(
        self,
        key: ConversationKey,
        *,
        operation_id: str,
        effect: EffectCheckpoint,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
        return await self._apply(
            key,
            lambda memory: memory.checkpoint(key, operation_id=operation_id, effect=effect),
            scope=coordination_scope,
            deadline=(lambda result: result.expires_at) if effect.state == "started" else None,
            operation_id=operation_id,
        )

    async def lookup_operation(self, key: ConversationKey, *, operation_id: str) -> ActionStatus:
        _, memory = await self._store.read(key, operation_id=operation_id)
        return await memory.lookup_operation(key, operation_id=operation_id)

    async def commit(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        mutation: NavigationMutation,
        coordination_scope: object | None = None,
    ) -> CommitResult:
        return await self._apply(
            key,
            lambda memory: memory.commit(key, expected_version=expected_version, mutation=mutation),
            scope=coordination_scope,
            deadline=lambda result: 0 if result.duplicate else result.snapshot.expires_at,
            operation_id=mutation.operation_id,
        )

    async def pending(self, key: ConversationKey) -> PreparedAction | None:
        _, memory = await self._store.read(key)
        return await memory.pending(key)

    async def mark_unknown(self, key: ConversationKey, *, operation_id: str) -> None:
        await self._apply(
            key,
            lambda memory: memory.mark_unknown(key, operation_id=operation_id),
            operation_id=operation_id,
        )

    async def abandon(
        self, key: ConversationKey, operation_id: str, *, expected_session_id: str
    ) -> None:
        await self._apply(
            key,
            lambda memory: memory.abandon(
                key, operation_id, expected_session_id=expected_session_id
            ),
            operation_id=operation_id,
        )

    async def reserve_token(
        self, key: ConversationKey, token: NavigationToken, *, operation_id: str
    ) -> NavigationToken:
        return await self._apply(
            key,
            lambda memory: memory.reserve_token(key, token, operation_id=operation_id),
            deadline=lambda result: result.expires_at,
            token=token.token,
            reservation_id=operation_id,
        )

    async def resolve_token(self, key: ConversationKey, token: str) -> NavigationToken | None:
        _, memory = await self._store.read(key, token=token)
        return await memory.resolve_token(key, token)

    async def consume_token(
        self, key: ConversationKey, token: str, *, actor_id: int, operation_id: str
    ) -> NavigationToken:
        return await self._apply(
            key,
            lambda memory: memory.consume_token(
                key, token, actor_id=actor_id, operation_id=operation_id
            ),
            deadline=lambda result: result.expires_at,
            token=token,
        )

    async def sweep(self, *, limit: int = 100) -> int:
        return await self._store.sweep(limit)

    async def close(self) -> None:
        if self.coordinator.active_scopes:
            raise ConfigurationError("Drain navigation scopes before closing Redis storage")
        if self._owned_client is not None:
            client, self._owned_client = self._owned_client, None
            await cast("_Closable", client).aclose()


class _Closable(Protocol):
    async def aclose(self) -> None: ...
