# pyright: reportUnknownMemberType=false
"""Redis 7+ authoritative idle backend; optional, navigation-independent storage."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING

from aiogram_coordination import ExternalSession

from ..config import IdleConfig
from ..errors import ConfigurationError, ConfigurationMismatch, VersionConflict
from ..models import (
    ActivityGuard,
    ActivitySnapshot,
    ConfigManifest,
    IdleConversationKey,
    RuntimeSnapshot,
    SessionGuard,
    SessionSnapshot,
)
from ..policies import IdlePolicy
from ..protocols import Coordinator
from ..registration import ActivityRegistration
from .activation import StorageMigrationPage, activate, format_manifest, migrate_records
from .deployment import RedisDeploymentAttestation
from .format import StorageActivation
from .redis_admin import IndexRecovery, IndexRecoveryPage
from .redis_coordinator import RedisCoordinator
from .redis_engine import Engine
from .redis_jobs import RedisJobs
from .redis_store import RedisStore
from .redis_transport import RedisClock
from .state import Claim, ControlToken, OperationLookup

if TYPE_CHECKING:
    pass


class RedisIdleBackend(RedisJobs):
    """Client-owned, single-primary Redis persistence with fenced job leases.

    Call initialize before constructing objects that consume clock.now(). Public
    asynchronous operations also initialize lazily. No local fallback exists.
    close does not close the caller's Redis connection.
    """

    capabilities = frozenset(
        {
            "opaque_components",
            "conditional_commits",
            "leases",
            "distributed",
            "component_transactions",
        }
    )

    def __init__(
        self,
        *,
        redis: object,
        prefix: str = "aiogram-idle",
        config: IdleConfig | None = None,
        deployment: RedisDeploymentAttestation | None = None,
        storage_format: int | None = None,
    ) -> None:
        if storage_format is not None and (type(storage_format) is not int or storage_format != 3):
            raise ConfigurationError("Fresh Redis storage_format must be 3 or auto (None)")
        self.config = config or IdleConfig()
        from ..engines import require_engine

        require_engine(self.config.engine)
        self._store = RedisStore(
            redis, prefix, self.config, deployment, requested_format=storage_format
        )
        self._owns_client = False
        self._index_recovery = IndexRecovery(self._store)
        self.clock: RedisClock = self._store.clock
        coordinator = RedisCoordinator(redis=redis, prefix=prefix)
        self.coordinator: Coordinator = coordinator
        self._store.fencer = coordinator.fencing
        self._store.migration_scope = coordinator.hold

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        prefix: str = "aiogram-idle",
        config: IdleConfig | None = None,
        deployment: RedisDeploymentAttestation | None = None,
        storage_format: int | None = None,
    ) -> RedisIdleBackend:
        """Create a backend; its client is exposed for explicit lifecycle ownership."""
        from redis.asyncio import Redis

        backend = cls(
            redis=Redis.from_url(url, socket_timeout=5, socket_connect_timeout=5),
            prefix=prefix,
            config=config,
            deployment=deployment,
            storage_format=storage_format,
        )
        backend._owns_client = True
        return backend

    @property
    def redis(self) -> object:
        return self._store.connection.client

    @property
    def active_storage_format(self) -> int:
        """Last observed namespace format; async storage_format refreshes authority."""
        return self._store.format_version

    async def initialize(self) -> None:
        await self._store.initialize()

    async def storage_format(self) -> int:
        await self.initialize()
        version, _, _ = await format_manifest(self._store)
        return version

    async def require_storage_format(self, version: int) -> None:
        if type(version) is not int or await self.storage_format() != version:
            raise ConfigurationMismatch("Requested feature requires activated storage format")

    async def activate_storage_format(
        self,
        *,
        operation_id: str,
        expected: int = 1,
        target: int = 2,
        old_workers_drained: bool = False,
        dry_run: bool = True,
    ) -> StorageActivation:
        await self.initialize()
        return await activate(
            self._store,
            expected=expected,
            target=target,
            operation_id=operation_id,
            old_workers_drained=old_workers_drained,
            dry_run=dry_run,
            active_scopes=self.coordinator.active_scopes,
        )

    async def migrate_storage_records(
        self, *, cursor: str = "0", limit: int = 100, dry_run: bool = True
    ) -> StorageMigrationPage:
        return await migrate_records(self._store, cursor=cursor, limit=limit, dry_run=dry_run)

    async def inspect_migration_backup(self, key: IdleConversationKey):
        from .cold_backup import inspect_backup

        return await inspect_backup(self._store, key)

    async def list_migration_backups(self, *, cursor: str = "0", limit: int = 32):
        from .cold_backup import list_backups

        return await list_backups(self._store, cursor=cursor, limit=limit)

    async def export_migration_backup(self, key: IdleConversationKey, *, expected_digest: str):
        from .cold_backup import export_backup

        return await export_backup(self._store, key, expected_digest=expected_digest)

    async def cleanup_migration_backup(
        self,
        key: IdleConversationKey,
        *,
        expected_digest: str,
        canonical_rows_verified: bool = False,
        unresolved_evidence_preserved: bool = False,
    ) -> bool:
        from .cold_backup import cleanup_backup

        return await cleanup_backup(
            self._store,
            key,
            expected_digest=expected_digest,
            canonical_rows_verified=canonical_rows_verified,
            unresolved_evidence_preserved=unresolved_evidence_preserved,
        )

    async def sweep_migration_staging(self, *, cursor: str = "0", limit: int = 32):
        from .cold_migration_gc import sweep_staging

        return await sweep_staging(self._store, cursor=cursor, limit=limit)

    async def canonical_component_migrate(
        self,
        key: IdleConversationKey,
        *,
        component: str,
        source_component: Mapping[str, object],
        target_component: Mapping[str, object],
        ledger_delta: Mapping[str, object],
        absolute_expiry: Mapping[str, int],
        limit: int = 32,
        dry_run: bool = True,
    ):
        from .canonical_migration import migrate

        return await migrate(
            self._store,
            key,
            component=component,
            source_component=source_component,
            target_component=target_component,
            ledger_delta=ledger_delta,
            absolute_expiry=absolute_expiry,
            limit=limit,
            dry_run=dry_run,
        )

    async def fused_activate(
        self,
        key: IdleConversationKey,
        registration: ActivityRegistration,
        *,
        external: ExternalSession | None,
        policy: IdlePolicy,
        operation_id: str,
        expected: ActivityGuard | None = None,
        enabled: bool = False,
        expected_manifest: str | None = None,
    ) -> ActivitySnapshot:
        return await self._store.mutate(
            key,
            lambda engine: engine.fused_activate(
                key,
                registration,
                external=external,
                policy=policy,
                operation_id=operation_id,
                expected=expected,
                enabled=enabled,
                expected_manifest=expected_manifest,
            ),
            require_live="session",
            arm=True,
            operation_id=operation_id,
        )

    async def bind_external_session(
        self,
        key: IdleConversationKey,
        *,
        session_id: str,
        revision: str,
        absolute_expires_at: int,
        operation_id: str,
    ) -> SessionSnapshot:
        return await self._store.mutate(
            key,
            lambda engine: engine.bind_external_session(
                key,
                session_id=session_id,
                revision=revision,
                absolute_expires_at=absolute_expires_at,
                operation_id=operation_id,
            ),
            operation_id=operation_id,
        )

    def bind_coordinator(self, coordinator: Coordinator) -> None:
        if coordinator is not self.coordinator:
            raise ConfigurationMismatch(
                "Redis backend requires its renewable distributed coordinator"
            )

    async def load(self, key: IdleConversationKey) -> RuntimeSnapshot | None:
        engine, _, _ = await self._store.read(key)
        if engine.stale_active():

            async def disarm(current: Engine) -> RuntimeSnapshot | None:
                current.disarm_stale()
                return await current.load(key)

            return await self._store.mutate(key, disarm)
        return await engine.load(key)

    async def open_session(
        self, key: IdleConversationKey, *, lifetime_seconds: float, operation_id: str
    ) -> SessionSnapshot:
        return await self._store.mutate(
            key,
            lambda engine: engine.open_session(
                key, lifetime_seconds=lifetime_seconds, operation_id=operation_id
            ),
            operation_id=operation_id,
        )

    async def replace_session(
        self,
        key: IdleConversationKey,
        *,
        expected: SessionGuard,
        lifetime_seconds: float,
        operation_id: str,
    ) -> SessionSnapshot:
        return await self._store.mutate(
            key,
            lambda engine: engine.replace_session(
                key, expected=expected, lifetime_seconds=lifetime_seconds, operation_id=operation_id
            ),
            require_live="session",
            operation_id=operation_id,
        )

    async def enter(
        self,
        key: IdleConversationKey,
        activity_key: str,
        *,
        policy_id: str,
        policy: IdlePolicy,
        adapter_key: str,
        params: Mapping[str, object],
        session_id: str,
        expires_at: float | datetime,
        operation_id: str,
        expected: ActivityGuard | None = None,
        enabled: bool = False,
        expected_manifest: str | None = None,
    ) -> ActivitySnapshot:
        from ..models import freeze_object

        frozen = freeze_object(params, max_bytes=self.config.max_params_bytes)
        return await self._store.mutate(
            key,
            lambda engine: engine.enter(
                key,
                activity_key,
                policy_id=policy_id,
                policy=policy,
                adapter_key=adapter_key,
                params=frozen,
                session_id=session_id,
                expires_at=expires_at,
                operation_id=operation_id,
                expected=expected,
                enabled=enabled,
                expected_manifest=expected_manifest,
            ),
            require_live=True,
            arm=True,
            operation_id=operation_id,
        )

    async def touch(
        self,
        key: IdleConversationKey,
        *,
        expected: ActivityGuard,
        operation_id: str,
        enabled: bool = False,
        expected_manifest: str | None = None,
    ) -> ActivitySnapshot:
        return await self._store.mutate(
            key,
            lambda engine: engine.touch(
                key,
                expected=expected,
                operation_id=operation_id,
                enabled=enabled,
                expected_manifest=expected_manifest,
            ),
            require_live=True,
            arm=True,
            operation_id=operation_id,
        )

    async def clear(
        self, key: IdleConversationKey, *, expected: ActivityGuard, operation_id: str, reason: str
    ) -> None:
        await self._store.mutate(
            key,
            lambda engine: engine.clear(
                key, expected=expected, operation_id=operation_id, reason=reason
            ),
            require_live=True,
            operation_id=operation_id,
        )

    async def transition(
        self,
        key: IdleConversationKey,
        *,
        expected_version: int,
        operation_id: str,
        fingerprint: str,
        transform: Callable[[RuntimeSnapshot], RuntimeSnapshot],
        claim: Claim | None = None,
        policy: IdlePolicy | None = None,
        coordination_scope: object | None = None,
    ) -> RuntimeSnapshot:
        async def reduce(engine: Engine) -> RuntimeSnapshot:
            engine.disarm_stale()
            return await engine.transition(
                key,
                expected_version=expected_version,
                operation_id=operation_id,
                fingerprint=fingerprint,
                transform=transform,
                claim=claim,
                policy=policy,
            )

        return await self._store.mutate(
            key,
            reduce,
            claim=claim,
            coordination_scope=coordination_scope,
            operation_id=operation_id,
        )

    async def component_transaction(
        self,
        key: IdleConversationKey,
        *,
        component: str,
        expected_version: int | None,
        operation_id: str,
        fingerprint: str,
        record: RuntimeSnapshot,
        policy: IdlePolicy | None = None,
        coordination_scope: object | None = None,
        expected_manifest: str | None = None,
        allow_idle_operation_id: str | None = None,
        expires_at: float | None = None,
        claim: Claim | None = None,
    ) -> RuntimeSnapshot:
        async def reduce(engine: Engine) -> RuntimeSnapshot:
            # The scratch reducer borrows validation only; Redis retains the real
            # task-scoped capability and atomically validates its fencing token.
            engine.coordinator = self.coordinator
            return await engine.component_transaction(
                key,
                component=component,
                expected_version=expected_version,
                operation_id=operation_id,
                fingerprint=fingerprint,
                record=record,
                policy=policy,
                expected_manifest=expected_manifest,
                allow_idle_operation_id=allow_idle_operation_id,
                expires_at=expires_at,
                coordination_scope=coordination_scope,
                claim=claim,
            )

        return await self._store.mutate(
            key,
            reduce,
            arm=True,
            coordination_scope=coordination_scope,
            expires_at=expires_at,
            claim=claim,
            operation_id=operation_id,
        )

    async def canonical_component_read(
        self,
        key: IdleConversationKey,
        *,
        component: str,
        operation_id: str = "",
        token: str = "",
        reservation_id: str = "",
        index_keys: tuple[str, ...] = (),
    ) -> Mapping[str, object]:
        await self.require_storage_format(3)
        from .canonical_redis import observe

        for _ in range(12):
            engine, raw, config = await self._store.read(key)
            try:
                return (
                    await observe(
                        self._store,
                        engine,
                        raw,
                        config,
                        component,
                        operation_id=operation_id,
                        token=token,
                        reservation_id=reservation_id,
                        index_keys=index_keys,
                    )
                ).payload
            except VersionConflict:
                continue
        raise VersionConflict("Canonical observation remained contended")

    async def canonical_component_transaction(
        self,
        key: IdleConversationKey,
        *,
        component: str,
        expected_version: int | None,
        record: RuntimeSnapshot,
        ledger_delta: Mapping[str, object],
        policy: IdlePolicy | None = None,
        coordination_scope: object | None = None,
        expected_manifest: str | None = None,
        allow_idle_operation_id: str | None = None,
        expires_at: float | None = None,
        claim: Claim | None = None,
        finalize_idle_operation_id: str | None = None,
    ) -> RuntimeSnapshot:
        await self.require_storage_format(3)

        async def reduce(engine: Engine) -> RuntimeSnapshot:
            engine.coordinator = self.coordinator
            return await engine.canonical_component_transaction(
                key,
                component=component,
                expected_version=expected_version,
                record=record,
                ledger_delta=ledger_delta,
                policy=policy,
                coordination_scope=coordination_scope,
                expected_manifest=expected_manifest,
                allow_idle_operation_id=allow_idle_operation_id,
                expires_at=expires_at,
                claim=claim,
                finalize_idle_operation_id=finalize_idle_operation_id,
            )

        return await self._store.mutate(
            key,
            reduce,
            coordination_scope=coordination_scope,
            expires_at=expires_at,
            claim=claim,
            arm=True,
            canonical=(component, ledger_delta),
        )

    async def lookup_operation(
        self, key: IdleConversationKey, operation_id: str, *, not_before: float | None = None
    ) -> OperationLookup:
        engine, _, _ = await self._store.read(key, operation_id=operation_id)
        return await engine.lookup_operation(key, operation_id, not_before=not_before)

    async def reserve_control(
        self,
        key: IdleConversationKey,
        *,
        token: str,
        prompt_id: str,
        activity_id: str,
        expires_at: float,
    ) -> ControlToken:
        return await self._store.mutate(
            key,
            lambda engine: engine.reserve_control(
                key,
                token=token,
                prompt_id=prompt_id,
                activity_id=activity_id,
                expires_at=expires_at,
            ),
            require_live=True,
        )

    async def resolve_control(self, key: IdleConversationKey, token: str) -> ControlToken | None:
        engine, _, _ = await self._store.read(key)
        return await engine.resolve_control(key, token)

    async def get_config(self) -> ConfigManifest | None:
        await self._store.ready()
        return self._store.config_value(await self._store.raw_config())

    async def bootstrap_config(self, *, enabled: bool, policies_digest: str) -> ConfigManifest:
        return await self._store.config_change(enabled=enabled, policies_digest=policies_digest)

    async def apply_config(
        self, *, expected_generation: str, enabled: bool, policies_digest: str, operation_id: str
    ) -> ConfigManifest:
        manifest = await self._store.config_change(
            enabled=enabled,
            policies_digest=policies_digest,
            expected=expected_generation,
            operation_id=operation_id,
        )
        if not enabled:
            await self.reconcile(limit=self.config.max_conversations)
        return manifest

    async def frozen_policy(self, key: IdleConversationKey) -> IdlePolicy:
        engine, _, _ = await self._store.read(key)
        return await engine.frozen_policy(key)

    async def inspect_parked(
        self, *, cursor: int = 0, limit: int = 100
    ) -> tuple[int, dict[IdleConversationKey, str]]:
        """Read a bounded Redis scan page of quarantined conversation reasons."""
        return await self._store.quarantine.inspect(cursor=cursor, limit=limit)

    async def release_parked(self, key: IdleConversationKey) -> None:
        """Explicitly release only after operator repair or a compatible upgrade."""
        await self._store.quarantine.release(key)

    async def close(self) -> None:
        """Close a from_url-owned client; caller-provided clients remain open."""
        if self.coordinator.active_scopes:
            raise ConfigurationError("Drain protected handlers before closing Redis storage")
        if self._owns_client:
            from redis.asyncio import Redis

            if isinstance(self.redis, Redis):
                await self.redis.aclose()
            self._owns_client = False

    async def recover_indexes(self, *, limit: int = 100) -> IndexRecoveryPage:
        """Explicit operator recovery; iterate until the returned page is complete."""
        return await self._index_recovery.run(limit=limit)
