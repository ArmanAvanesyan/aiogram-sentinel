"""Navigation reduction followed by one idle-owned atomic component commit."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import contextvars
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

from aiogram_nav.clock import ManualClock
from aiogram_nav.errors import ConfigurationError, SessionExpired, VersionConflict
from aiogram_nav.models import CommitResult, ConversationKey, PreparedAction, VersionedSnapshot
from aiogram_nav.storage.memory import MemoryNavigationRepository

from ...errors import VersionConflict as IdleVersionConflict
from ...models import RuntimeSnapshot
from ...policies import IdlePolicy
from ...storage.state import Claim
from .codec import COMPONENT, OWNER, component, load_ledger, save_component

if TYPE_CHECKING:
    from .repository import NavigationRepository

T = TypeVar("T")
STAGING_CLAIM: contextvars.ContextVar[Claim | None] = contextvars.ContextVar(
    "idle_nav_claim", default=None
)
STAGING: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "idle_nav_staging", default=None
)


class ComponentBackend(Protocol):
    async def component_transaction(
        self,
        key: object,
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


def reducer(
    repo: NavigationRepository, key: ConversationKey, current: RuntimeSnapshot | None
) -> MemoryNavigationRepository:
    memory = MemoryNavigationRepository(clock=ManualClock(repo.clock.now()), config=repo.config)
    ledger = load_ledger(current, key, expected_profile=repo.profile)
    if ledger is not None:
        memory._records[key] = ledger
    return memory


async def apply(
    repo: NavigationRepository,
    key: ConversationKey,
    callback: Callable[[MemoryNavigationRepository], Awaitable[T]],
    *,
    scope: object | None = None,
    deadline: Callable[[T], int] | None = None,
    accepted: bool = False,
    restart: bool = False,
) -> T:
    from .lifecycle import compose

    await repo.idle.initialize()
    idle_key = repo.mapping.to_idle(key)
    if STAGING.get() is not None and (scope or repo.coordinator.scope_token(key)) is None:
        from aiogram_nav.errors import OwnershipLost

        raise OwnershipLost("Copied staging context does not grant conversation ownership")
    for _ in range(16):
        current = await repo.idle.backend.load(idle_key)
        memory = reducer(repo, key, current)
        from .sessions import binding, observe, seed

        external = await observe(repo, key)
        await seed(repo, key, current, memory, external)
        old_ledger = memory._records.get(key)
        old_ids: set[str] = set(old_ledger.operations) if old_ledger else set()
        previous_nav = (
            old_ledger.current.snapshot
            if old_ledger is not None and old_ledger.current is not None
            else None
        )
        old_component = component(current, expected_profile=repo.profile)
        old_raw = str(old_component["ledger"]) if old_component else None
        result = await callback(memory)
        ledger = memory._records.get(key)
        if ledger is None:
            raise ConfigurationError("Integrated navigation cannot discard its recovery ledger")
        if isinstance(result, PreparedAction) and result.operation_id not in old_ids:
            expiry = result.expires_at
            session_id = result.session_id
            source_binding = binding(current)
            if (
                current is not None
                and current.session.expires_at > repo.idle.clock.now()
                and (
                    external is None
                    or (
                        source_binding is not None
                        and source_binding.get("session_id") == external.session_id
                    )
                )
            ):
                session_id = current.session.session_id
                cap = int(current.session.expires_at * 1000)
                if result.intent.expires_at is not None and expiry > cap:
                    raise SessionExpired("Navigation expiry exceeds its authoritative session")
                expiry = min(expiry, cap)
            normalized = replace(result, session_id=session_id, expires_at=expiry)
            ledger.operations[normalized.operation_id].prepared = normalized
            result = cast(T, normalized)
        if (
            isinstance(result, CommitResult)
            and not result.duplicate
            and previous_nav is not None
            and previous_nav.session_id == result.snapshot.session_id
            and previous_nav.expires_at <= repo.clock.now()
            and result.snapshot.nav_revision <= previous_nav.nav_revision
        ):
            normalized_snapshot = replace(
                result.snapshot, nav_revision=previous_nav.nav_revision + 1
            )
            normalized_result = replace(result, snapshot=normalized_snapshot)
            ledger.current = VersionedSnapshot(normalized_snapshot, ledger.version)
            for entry in ledger.operations.values():
                if entry.result is result:
                    entry.result = normalized_result
            result = cast(T, normalized_result)
        effective_accepted = accepted and not (
            isinstance(result, CommitResult) and result.duplicate
        )
        if effective_accepted and isinstance(result, CommitResult):
            operation = next(
                (entry for entry in ledger.operations.values() if entry.result is result), None
            )
            if operation is not None and operation.prepared is not None:
                effective_accepted = operation.prepared.intent.accepted_activity
            if (
                effective_accepted
                and current is not None
                and current.activity is not None
                and current.session.session_id == result.snapshot.session_id
            ):
                revision = current.activity.activity_revision + 1
                if result.snapshot.activity_revision != revision:
                    normalized_snapshot = replace(result.snapshot, activity_revision=revision)
                    normalized_result = replace(result, snapshot=normalized_snapshot)
                    ledger.current = VersionedSnapshot(normalized_snapshot, ledger.version)
                    if operation is not None:
                        operation.result = normalized_result
                    result = cast(T, normalized_result)
        from .overlay import active as reply_overlay_active
        from .overlay import prepare as prepare_overlay

        reply_overlay = reply_overlay_active(current)
        completed_operation = next(
            (
                name
                for name, entry in ledger.operations.items()
                if isinstance(result, CommitResult) and entry.result is result
            ),
            None,
        )
        if (
            effective_accepted
            and completed_operation is not None
            and ledger.operations[completed_operation].prepared is None
            and reply_overlay
        ):
            await prepare_overlay(memory, key, completed_operation)
        elif (
            isinstance(result, CommitResult)
            and not result.duplicate
            and completed_operation is not None
            and ledger.operations[completed_operation].prepared is not None
        ):
            reply_overlay = False
        if external is not None:
            ledger.external_session = replace(external, idle_expires_at=None)
        value = save_component(ledger, key, expected_profile=repo.profile)
        if old_raw == value["ledger"]:
            if scope is not None and not repo.coordinator.scope_matches(key, scope):
                from aiogram_nav.errors import OwnershipLost

                raise OwnershipLost("Navigation coordination capability expired")
            return result
        manifest = await repo.idle.manifest()
        accepted_operation = next(
            (
                name
                for name, entry in ledger.operations.items()
                if isinstance(result, CommitResult) and entry.result is result
            ),
            None,
        )
        desired, policy = compose(
            repo,
            key,
            current,
            ledger,
            value,
            accepted=effective_accepted,
            enabled=manifest.enabled,
            restart=restart,
            operation_id=accepted_operation,
            reply_overlay=reply_overlay,
        )
        marker = desired.components[OWNER]
        # Compose creates the component marker.
        assert isinstance(marker, dict) or hasattr(marker, "get")  # nosec B101
        raw = str(value["ledger"])
        digest = hashlib.sha256((str(current.version if current else 0) + raw).encode()).hexdigest()
        expiry = deadline(result) / 1000 if deadline is not None else None
        # Duplicate navigation receipts are returned without a transaction above.
        try:
            committed = await cast(ComponentBackend, repo.idle.backend).component_transaction(
                idle_key,
                component=COMPONENT,
                expected_version=current.version if current else None,
                operation_id="nav:" + digest,
                fingerprint=digest,
                record=desired,
                policy=policy,
                coordination_scope=scope or repo.coordinator.scope_token(key),
                expected_manifest=manifest.generation,
                allow_idle_operation_id=STAGING.get(),
                expires_at=expiry,
                claim=STAGING_CLAIM.get(),
            )
            if (
                effective_accepted
                and current is not None
                and current.idle.prompt is not None
                and committed.idle.prompt is None
            ):
                authority = scope or repo.coordinator.scope_token(key)
                if authority is not None and repo.coordinator.scope_matches(key, authority):
                    try:
                        await repo.idle.presenter.strip(current.idle.prompt)
                    except Exception:
                        import logging

                        logging.getLogger(__name__).warning(
                            "Superseded integrated prompt cleanup unavailable"
                        )
            return result
        except IdleVersionConflict:
            continue
    raise VersionConflict("Integrated navigation contention limit reached")
