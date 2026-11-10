"""Generic atomic component projection; core never interprets component content."""

from __future__ import annotations

# This mixin is the backend-owned implementation of the private storage protocol.
# pyright: reportPrivateUsage=false
import asyncio
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol, cast

from ..config import IdleConfig
from ..errors import (
    ActivityConflict,
    ConfigurationError,
    OwnershipLost,
    SessionExpired,
    VersionConflict,
)
from ..models import (
    ConfigManifest,
    IdleConversationKey,
    IdleSnapshot,
    Phase,
    RuntimeSnapshot,
    freeze_object,
    timestamp,
)
from ..policies import ExemptPolicy, IdlePolicy
from ..protocols import Coordinator
from .base import IdleBackend
from .codec import encode
from .coordination import check_manifest
from .receipts import Receipts
from .receipts import fingerprint as value_fingerprint
from .retention import PENDING_PHASES
from .state import Claim

if TYPE_CHECKING:
    from .queue import DeadlineQueue

OWNER_COMPONENT = "__idle_owner__"


def ownership(record: RuntimeSnapshot) -> Mapping[str, object] | None:
    value = record.components.get(OWNER_COMPONENT)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ConfigurationError("Malformed component ownership marker")
    marker = cast(Mapping[str, object], value)
    if (
        not isinstance(marker.get("component"), str)
        or not marker["component"]
        or len(cast(str, marker["component"])) > 128
        or type(marker.get("pending")) is not bool
        or ("parked" in marker and type(marker["parked"]) is not bool)
    ):
        raise ConfigurationError("Malformed component ownership marker")
    timestamp(cast(float, marker.get("retain_until", 0)))
    if marker.get("pending") is True:
        timestamp(cast(float, marker.get("recovery_at")))
    return marker


def component_deadline(record: RuntimeSnapshot) -> float | None:
    marker = ownership(record)
    if marker is not None and marker.get("pending") is True and marker.get("parked") is True:
        return None
    if marker is not None and marker.get("pending") is True and record.idle.operation is None:
        return timestamp(cast(float, marker["recovery_at"]))
    return record.idle.deadline


class ComponentOwner(Protocol):
    config: IdleConfig
    coordinator: Coordinator
    _lock: asyncio.Lock
    _records: dict[IdleConversationKey, RuntimeSnapshot]
    _receipts: Receipts
    _manifest: ConfigManifest | None
    _policies: dict[IdleConversationKey, IdlePolicy]
    _queue: DeadlineQueue

    def _now(self) -> float: ...
    def _capacity(self) -> None: ...
    def _save(self, record: RuntimeSnapshot, *, claim: Claim | None = None) -> RuntimeSnapshot: ...


class ComponentTransactions:
    """Mixin requiring the same authoritative lock and scheduling path as activity."""

    async def component_transaction(
        self: ComponentOwner,
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
        if (
            not isinstance(cast(object, component), str)
            or not component
            or component == OWNER_COMPONENT
            or len(component) > 128
        ):
            raise ConfigurationError("Component name must be a bounded owned slot")
        if expected_version is not None and (
            type(expected_version) is not int or expected_version < 1
        ):
            raise ConfigurationError("Component expected version must be positive or absent")
        if (
            not isinstance(cast(object, fingerprint), str)
            or not fingerprint
            or len(fingerprint) > 256
        ):
            raise ConfigurationError("Component fingerprint must contain 1 to 256 characters")
        marker = ownership(record)
        if marker is None or marker["component"] != component or component not in record.components:
            raise ConfigurationError("Component commit requires its ownership marker and payload")
        freeze_object(record.components, max_bytes=self.config.max_components_bytes)
        if record.key != key:
            raise ActivityConflict("Component commit changed conversation identity")
        async with self._lock:
            if allow_idle_operation_id is not None and coordination_scope is None:
                raise OwnershipLost("Staged component writes require an owned conversation scope")
            if coordination_scope is not None and not self.coordinator.scope_matches(
                key, coordination_scope
            ):
                raise OwnershipLost("Component coordination scope ended")
            now = self._now()
            if claim is not None:
                if claim.key != key:
                    raise OwnershipLost("Component claim belongs to another conversation")
                self._queue.check(claim, now)
            duplicate = self._receipts.prepare(key, operation_id, fingerprint, now=now)
            if duplicate is not None:
                return cast(RuntimeSnapshot, duplicate)
            if expires_at is not None and timestamp(expires_at) <= now:
                raise SessionExpired("Component authorization expired")
            if record.session.expires_at <= now and expected_version is None:
                raise SessionExpired("New component session is expired")
            check_manifest(self._manifest.generation if self._manifest else None, expected_manifest)
            previous = self._records.get(key)
            if (previous.store_version if previous else None) != expected_version:
                raise VersionConflict("Component runtime version changed")
            if previous is None:
                self._capacity()
            else:
                old_marker = ownership(previous)
                if old_marker is not None and old_marker["component"] != component:
                    raise ActivityConflict("Another component owns this activity slot")
                if old_marker is None and previous.activity is not None:
                    raise ActivityConflict("Cannot adopt an existing standalone activity")
                if (
                    previous.idle.operation is not None
                    and previous.idle.phase
                    in PENDING_PHASES | {Phase.ACTIVE, Phase.EFFECT_UNKNOWN, Phase.QUARANTINED}
                    and previous.idle.operation.operation_id != allow_idle_operation_id
                ):
                    raise ActivityConflict("An idle operation owns the component slot")
                if previous.idle.operation is not None and (
                    encode(previous.idle) != encode(record.idle)
                    or encode(previous.activity) != encode(record.activity)
                ):
                    raise ActivityConflict(
                        "Staged components cannot replace the idle operation or activity"
                    )
                if set(record.components) - set(previous.components) - {component, OWNER_COMPONENT}:
                    raise ActivityConflict("Component commit added an unrelated slot")
                if (
                    previous.session.session_id == record.session.session_id
                    and previous.session.expires_at != record.session.expires_at
                ):
                    raise ActivityConflict("Component commit cannot change absolute session expiry")
                if previous.session != record.session and previous.session.expires_at > now:
                    raise ActivityConflict("Component commit cannot replace a live session")
                for name, value in previous.components.items():
                    if name not in {component, OWNER_COMPONENT} and value_fingerprint(
                        record.components.get(name)
                    ) != value_fingerprint(value):
                        raise ActivityConflict("Component commit changed an unrelated slot")
            if record.activity is not None:
                activity = record.activity
                if (
                    activity.session_id != record.session.session_id
                    or activity.expires_at > record.session.expires_at
                ):
                    raise ActivityConflict("Component activity differs from immutable session")
                if (previous is None or previous.activity != activity) and min(
                    activity.expires_at, record.session.expires_at
                ) <= now:
                    raise SessionExpired("Component acceptance cannot revive expired activity")
                if policy is None and key not in self._policies:
                    raise ConfigurationError(
                        "Component activity requires an explicit frozen policy"
                    )
            effective_policy = policy or self._policies.get(key)
            enabled = self._manifest.enabled if self._manifest else self.config.enabled
            if record.idle.phase == Phase.ACTIVE and (
                not enabled or isinstance(effective_policy, ExemptPolicy)
            ):
                record = replace(record, idle=IdleSnapshot())
            updated = self._save(
                replace(
                    record,
                    recovery_until=max(
                        record.recovery_until, timestamp(cast(float, marker.get("retain_until", 0)))
                    ),
                ),
                claim=claim,
            )
            if policy is not None:
                self._policies[key] = policy
            return self._receipts.save(key, operation_id, fingerprint, updated, now=now)


class ComponentBackend(IdleBackend, Protocol):
    """Optional backend capability; standalone custom backends need not implement it."""

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
    ) -> RuntimeSnapshot: ...
