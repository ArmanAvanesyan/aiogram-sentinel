"""Atomic single-process idle storage with bounded recovery evidence."""

from __future__ import annotations

import asyncio
import math
import secrets
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, cast

from ..clock import Clock, SystemClock
from ..config import IdleConfig
from ..coordinator import MemoryCoordinator
from ..errors import (
    ActivityConflict,
    ConfigurationError,
    ConfigurationMismatch,
    Overloaded,
    OwnershipLost,
    SessionExpired,
    VersionConflict,
)
from ..models import (
    ActivityGuard,
    ActivitySnapshot,
    ConfigManifest,
    IdleConversationKey,
    IdleSnapshot,
    Phase,
    RuntimeSnapshot,
    SessionGuard,
    SessionSnapshot,
    freeze_object,
    timestamp,
)
from ..policies import ExemptPolicy, PromptPolicy, QuietRestorePolicy
from ..protocols import Coordinator
from .canonical import CanonicalComponents, CanonicalRows
from .component_transaction import ComponentTransactions, component_deadline
from .control_tokens import reserve, resolve
from .coordination import bind, check_manifest
from .format import StorageFormats
from .fused_activity import FusedActivities
from .owned_lock import OwnedLock
from .queue import DeadlineQueue
from .receipts import Receipts, fingerprint, lookup_operation
from .retention import ensure_activity_mutable, may_prune
from .session_bindings import SessionBindings
from .state import Claim, ControlToken, OperationLookup

if TYPE_CHECKING:
    from .canonical_memory_migration import MigrationStage


Policy = ExemptPolicy | PromptPolicy | QuietRestorePolicy


class MemoryIdleBackend(
    StorageFormats, SessionBindings, ComponentTransactions, FusedActivities, CanonicalComponents
):
    """Memory backend. Share one instance within one process only."""

    capabilities = frozenset(
        {"opaque_components", "conditional_commits", "leases", "component_transactions"}
    )

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        config: IdleConfig | None = None,
        storage_format: int = 1,
    ) -> None:
        if type(storage_format) is not int or storage_format not in (1, 3):
            raise ConfigurationError("Fresh memory storage_format must be 1 or 3")
        self.config = config or IdleConfig()
        from ..engines import make_queue, require_engine

        require_engine(self.config.engine)
        self.clock = clock or SystemClock()
        self._created_at = self.clock.now()
        self._storage_format = storage_format
        self._activation_operation: str | None = None
        self._lock: asyncio.Lock = OwnedLock()
        self.coordinator: Coordinator = MemoryCoordinator()
        self._records: dict[IdleConversationKey, RuntimeSnapshot] = {}
        self._canonical_migrations: dict[tuple[IdleConversationKey, str], MigrationStage] = {}
        self._canonical_rows: dict[tuple[IdleConversationKey, str], CanonicalRows] = {}
        self._queue: DeadlineQueue = make_queue(self.config.engine)
        self._receipts = Receipts(
            limit=self.config.max_receipts_per_conversation,
            retention=self.config.effective_replay_retention_seconds,
            engine=self.config.engine,
        )
        self._policies: dict[IdleConversationKey, Policy] = {}
        self._tokens: dict[IdleConversationKey, dict[str, ControlToken]] = {}
        self._manifest: ConfigManifest | None = None
        self._config_receipts = Receipts(
            limit=self.config.max_receipts_per_conversation,
            retention=self.config.effective_replay_retention_seconds,
            engine=self.config.engine,
        )
        self._reconcile_cursor = 0

    @property
    def active_storage_format(self) -> int:
        return self._storage_format

    def _now(self) -> float:
        return self.clock.now()

    def _get(self, key: IdleConversationKey, *, live: bool = True) -> RuntimeSnapshot:
        record = self._records.get(key)
        if live:
            from ..engines import session_guard

            failure = session_guard(
                (record.session.session_id, record.session.revision, record.session.expires_at)
                if record
                else None,
                None,
                self._now(),
                engine=self.config.engine,
            )
            if failure is not None:
                raise SessionExpired("No live session exists")
        if record is None:
            raise SessionExpired("No live session exists")
        return record

    def _guard(self, record: RuntimeSnapshot, expected: ActivityGuard) -> ActivitySnapshot:
        activity = record.activity
        from ..engines import activity_guard

        failure = activity_guard(
            (
                activity.session_id,
                activity.activity_id,
                activity.activity_revision,
                activity.expires_at,
            )
            if activity
            else None,
            (expected.session_id, expected.activity_id, expected.activity_revision),
            self._now(),
            engine=self.config.engine,
        )
        if failure == "conflict":
            raise ActivityConflict("The activity generation or revision changed")
        if failure == "expired":
            raise SessionExpired("The activity expired")
        assert activity is not None
        return activity

    def _fingerprint(self, value: object) -> str:
        return fingerprint(value, engine=self.config.engine)

    def _save(self, record: RuntimeSnapshot, *, claim: Claim | None = None) -> RuntimeSnapshot:
        freeze_object(record.components, max_bytes=self.config.max_components_bytes)
        previous = self._records.get(record.key)
        updated = replace(
            record,
            store_version=(previous.store_version + 1 if previous else 1),
            recovery_until=max(
                record.recovery_until, self._now() + self.config.recovery_retention_seconds
            ),
        )
        self._queue.schedule(updated, preserve=claim)
        self._records[record.key] = updated
        return updated

    def _deadline(self, policy: Policy, *, enabled: bool, now: float) -> IdleSnapshot:
        if not (self._manifest.enabled if self._manifest else enabled) or isinstance(
            policy, ExemptPolicy
        ):
            return IdleSnapshot()
        return IdleSnapshot(phase=Phase.ACTIVE, deadline=now + policy.after_seconds)

    def _capacity(self) -> None:
        now = self._now()
        for key, record in tuple(self._records.items()):
            if may_prune(record, self._queue.jobs.get(key), now):
                self._records.pop(key)
                self._queue.jobs.pop(key, None)
                self._tokens.pop(key, None)
                self._policies.pop(key, None)
                self._receipts.items.pop(key, None)
        if len(self._records) >= self.config.max_conversations:
            raise Overloaded(
                "Conversation capacity is exhausted",
                reason="protected_evidence",
                limit=self.config.max_conversations,
                used=len(self._records),
                protected_evidence=len(self._records),
            )

    async def load(self, key: IdleConversationKey) -> RuntimeSnapshot | None:
        async with self._lock:
            return self._records.get(key)

    async def open_session(
        self, key: IdleConversationKey, *, lifetime_seconds: float, operation_id: str
    ) -> SessionSnapshot:
        if (
            isinstance(lifetime_seconds, bool)
            or not math.isfinite(lifetime_seconds)
            or lifetime_seconds <= 0
        ):
            raise ValueError("Session lifetime must be positive")
        async with self._lock:
            now = self._now()
            digest = self._fingerprint(("open", lifetime_seconds))
            duplicate = self._receipts.prepare(key, operation_id, digest, now=now)
            if duplicate is not None:
                return cast(SessionSnapshot, duplicate)
            existing = self._records.get(key)
            if existing is not None:
                ensure_activity_mutable(existing)
            if existing is not None and existing.session.expires_at > now:
                raise ActivityConflict("A live session already exists")
            if existing is None:
                self._capacity()
            session = SessionSnapshot(secrets.token_urlsafe(18), now + lifetime_seconds)
            self._save(RuntimeSnapshot(key=key, session=session))
            return self._receipts.save(key, operation_id, digest, session, now=now)

    async def replace_session(
        self,
        key: IdleConversationKey,
        *,
        expected: SessionGuard,
        lifetime_seconds: float,
        operation_id: str,
    ) -> SessionSnapshot:
        if (
            isinstance(lifetime_seconds, bool)
            or not math.isfinite(lifetime_seconds)
            or lifetime_seconds <= 0
        ):
            raise ValueError("Session lifetime must be positive")
        async with self._lock:
            now = self._now()
            digest = self._fingerprint(("replace_session", expected, lifetime_seconds))
            duplicate = self._receipts.prepare(key, operation_id, digest, now=now)
            if duplicate is not None:
                return cast(SessionSnapshot, duplicate)
            previous = self._get(key)
            ensure_activity_mutable(previous)
            if previous.session.guard != expected:
                raise ActivityConflict("Session generation changed")
            session = SessionSnapshot(secrets.token_urlsafe(18), now + lifetime_seconds)
            self._save(RuntimeSnapshot(key=key, session=session, components=previous.components))
            return self._receipts.save(key, operation_id, digest, session, now=now)

    async def enter(
        self,
        key: IdleConversationKey,
        activity_key: str,
        *,
        policy_id: str,
        policy: Policy,
        adapter_key: str,
        params: Mapping[str, object],
        session_id: str,
        expires_at: float | datetime,
        operation_id: str,
        expected: ActivityGuard | None = None,
        enabled: bool = False,
        expected_manifest: str | None = None,
    ) -> ActivitySnapshot:
        expiry = timestamp(expires_at)
        frozen = freeze_object(params, max_bytes=self.config.max_params_bytes)
        async with self._lock:
            now = self._now()
            digest = self._fingerprint(
                (
                    "enter",
                    activity_key,
                    policy_id,
                    policy,
                    adapter_key,
                    frozen,
                    session_id,
                    expiry,
                    expected,
                )
            )
            duplicate = self._receipts.prepare(key, operation_id, digest, now=now)
            if duplicate is not None:
                return cast(ActivitySnapshot, duplicate)
            check_manifest(self._manifest.generation if self._manifest else None, expected_manifest)
            record = self._get(key)
            ensure_activity_mutable(record)
            if record.session.session_id != session_id:
                raise ActivityConflict("Session generation changed")
            if expected is not None:
                self._guard(record, expected)
            elif record.activity is not None and record.activity.expires_at > now:
                raise ActivityConflict("Entering over a live activity requires its guard")
            if expiry <= now or expiry > record.session.expires_at:
                raise ValueError("Activity expiry must fit inside the live session")
            activity = ActivitySnapshot(
                session_id=session_id,
                activity_id=secrets.token_urlsafe(18),
                activity_key=activity_key,
                activity_revision=1,
                policy_id=policy_id,
                adapter_key=adapter_key,
                params=frozen,
                entered_at=now,
                last_activity_at=now,
                expires_at=expiry,
            )
            self._policies[key] = policy
            self._save(
                replace(
                    record, activity=activity, idle=self._deadline(policy, enabled=enabled, now=now)
                )
            )
            return self._receipts.save(key, operation_id, digest, activity, now=now)

    async def touch(
        self,
        key: IdleConversationKey,
        *,
        expected: ActivityGuard,
        operation_id: str,
        enabled: bool = False,
        expected_manifest: str | None = None,
    ) -> ActivitySnapshot:
        async with self._lock:
            now = self._now()
            digest = self._fingerprint(("touch", expected))
            duplicate = self._receipts.prepare(key, operation_id, digest, now=now)
            if duplicate is not None:
                return cast(ActivitySnapshot, duplicate)
            check_manifest(self._manifest.generation if self._manifest else None, expected_manifest)
            record = self._get(key)
            ensure_activity_mutable(record)
            activity = self._guard(record, expected)
            activity = replace(
                activity, activity_revision=activity.activity_revision + 1, last_activity_at=now
            )
            self._save(
                replace(
                    record,
                    activity=activity,
                    idle=self._deadline(self._policies[key], enabled=enabled, now=now),
                )
            )
            return self._receipts.save(key, operation_id, digest, activity, now=now)

    async def clear(
        self, key: IdleConversationKey, *, expected: ActivityGuard, operation_id: str, reason: str
    ) -> None:
        async with self._lock:
            now = self._now()
            digest = self._fingerprint(("clear", expected, reason))
            duplicate = self._receipts.prepare(key, operation_id, digest, now=now)
            if duplicate is not None:
                return
            record = self._get(key)
            ensure_activity_mutable(record)
            self._guard(record, expected)
            self._save(replace(record, activity=None, idle=IdleSnapshot()))
            self._receipts.save(key, operation_id, digest, True, now=now)

    async def transition(
        self,
        key: IdleConversationKey,
        *,
        expected_version: int,
        operation_id: str,
        fingerprint: str,
        transform: Callable[[RuntimeSnapshot], RuntimeSnapshot],
        claim: Claim | None = None,
        policy: Policy | None = None,
        coordination_scope: object | None = None,
    ) -> RuntimeSnapshot:
        async with self._lock:
            if coordination_scope is not None and not self.coordinator.scope_matches(
                key, coordination_scope
            ):
                raise OwnershipLost("Delegated effect coordination scope ended")
            now = self._now()
            if claim is not None:
                if claim.key != key:
                    raise OwnershipLost("Claim belongs to another conversation")
                self._queue.check(claim, now)
            duplicate = self._receipts.prepare(key, operation_id, fingerprint, now=now)
            if duplicate is not None:
                return cast(RuntimeSnapshot, duplicate)
            record = self._get(key, live=False)
            if record.store_version != expected_version:
                raise VersionConflict("Runtime version changed")
            changed = transform(record)
            if changed.key != key or changed.session.session_id != record.session.session_id:
                raise ActivityConflict(
                    "Worker transition cannot replace conversation/session identity"
                )
            updated = self._save(changed, claim=claim)
            if policy is not None:
                self._policies[key] = policy
            return self._receipts.save(key, operation_id, fingerprint, updated, now=now)

    async def claim_due(
        self,
        *,
        limit: int,
        lease_seconds: float,
        namespace: str | None = None,
        bot_id: int | None = None,
    ) -> list[Claim]:
        if (
            isinstance(limit, bool)
            or limit < 1
            or not math.isfinite(lease_seconds)
            or lease_seconds <= 0
        ):
            raise ValueError("Claim capacity and lease must be positive")
        async with self._lock:
            return self._queue.claim(
                limit=limit,
                lease_seconds=lease_seconds,
                now=self._now(),
                namespace=namespace,
                bot_id=bot_id,
            )

    async def renew_claim(self, claim: Claim, *, lease_seconds: float) -> Claim:
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("Lease must be positive")
        async with self._lock:
            return self._queue.renew(claim, now=self._now(), lease_seconds=lease_seconds)

    async def validate_claim(self, claim: Claim) -> None:
        async with self._lock:
            self._queue.check(claim, self._now())

    async def release_claim(self, claim: Claim, *, retry_at: float | None = None) -> None:
        async with self._lock:
            self._queue.release(
                claim, self._get(claim.key, live=False), now=self._now(), retry_at=retry_at
            )

    async def lookup_operation(
        self, key: IdleConversationKey, operation_id: str, *, not_before: float | None = None
    ) -> OperationLookup:
        async with self._lock:
            return lookup_operation(
                self._receipts,
                key,
                operation_id,
                now=self._now(),
                created_at=self._created_at,
                not_before=not_before,
            )

    async def reserve_control(
        self,
        key: IdleConversationKey,
        *,
        token: str,
        prompt_id: str,
        activity_id: str,
        expires_at: float,
    ) -> ControlToken:
        async with self._lock:
            record = self._get(key)
            return reserve(
                record,
                self._tokens.setdefault(key, {}),
                token=token,
                prompt_id=prompt_id,
                activity_id=activity_id,
                expires_at=expires_at,
                now=self._now(),
                limit=self.config.max_tokens_per_conversation,
            )

    async def resolve_control(self, key: IdleConversationKey, token: str) -> ControlToken | None:
        async with self._lock:
            return resolve(
                self._records.get(key), self._tokens.get(key, {}).get(token), now=self._now()
            )

    async def bootstrap_config(self, *, enabled: bool, policies_digest: str) -> ConfigManifest:
        async with self._lock:
            if self._manifest is None:
                self._manifest = ConfigManifest(secrets.token_urlsafe(12), enabled, policies_digest)
            elif (
                self._manifest.enabled != enabled
                or self._manifest.policies_digest != policies_digest
            ):
                raise ConfigurationMismatch(
                    "Stored configuration differs from startup configuration"
                )
            return self._manifest

    async def apply_config(
        self, *, expected_generation: str, enabled: bool, policies_digest: str, operation_id: str
    ) -> ConfigManifest:
        async with self._lock:
            digest = self._fingerprint((expected_generation, enabled, policies_digest))
            duplicate = self._config_receipts.prepare(
                "configuration", operation_id, digest, now=self._now()
            )
            if duplicate is not None:
                return cast(ConfigManifest, duplicate)
            if self._manifest is None or self._manifest.generation != expected_generation:
                raise ConfigurationMismatch("Configuration generation changed")
            self._manifest = ConfigManifest(secrets.token_urlsafe(12), enabled, policies_digest)
            self._config_receipts.save(
                "configuration", operation_id, digest, self._manifest, now=self._now()
            )
            if not enabled:
                for record in tuple(self._records.values()):
                    if record.idle.phase == Phase.ACTIVE:
                        self._save(replace(record, idle=IdleSnapshot()))
            return self._manifest

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
        from .canonical_memory_migration import migrate

        return await migrate(
            self,
            key,
            component=component,
            source_component=source_component,
            target_component=target_component,
            ledger_delta=ledger_delta,
            absolute_expiry=absolute_expiry,
            limit=limit,
            dry_run=dry_run,
        )

    async def reconcile(self, *, limit: int = 100) -> int:
        """Repair missing due jobs and prune bounded expired state."""
        if limit < 1:
            raise ValueError("Reconciliation limit must be positive")
        async with self._lock:
            keys = list(self._records)
            if not keys:
                return 0
            start = self._reconcile_cursor % len(keys)
            selected = (keys[start:] + keys[:start])[:limit]
            self._reconcile_cursor = start + len(selected)
            repaired = 0
            now = self._now()
            for key in selected:
                record = self._records[key]
                canonical_retained = any(
                    any(
                        operation_id not in rows.expiry or rows.expiry[operation_id] > now * 1000
                        for operation_id in rows.known_ids
                    )
                    for name in record.components
                    if (rows := self._canonical_rows.get((key, name))) is not None
                )
                if not canonical_retained and may_prune(record, self._queue.jobs.get(key), now):
                    self._records.pop(key)
                    self._queue.jobs.pop(key, None)
                    self._policies.pop(key, None)
                    self._tokens.pop(key, None)
                    self._receipts.items.pop(key, None)
                    for name in record.components:
                        self._canonical_rows.pop((key, name), None)
                elif component_deadline(record) is not None and key not in self._queue.jobs:
                    self._queue.schedule(record)
                    repaired += 1
                for token, value in tuple(self._tokens.get(key, {}).items()):
                    if value.expires_at <= now:
                        del self._tokens[key][token]
            return repaired

    async def close(self) -> None:
        """A caller-owned memory backend retains state until it is discarded."""

    async def frozen_policy(self, key: IdleConversationKey) -> Policy:
        async with self._lock:
            self._get(key)
            return self._policies[key]

    async def get_config(self) -> ConfigManifest | None:
        async with self._lock:
            return self._manifest

    def bind_coordinator(self, coordinator: Coordinator) -> None:
        self.coordinator = bind(self.coordinator, coordinator, has_records=bool(self._records))
        self._explicit_coordinator = True
