"""Bounded single-process canonical migration, with an immutable source until cutover."""

from __future__ import annotations

# This reducer owns its backend scratch state under the backend task-owned lock.
# pyright: reportPrivateUsage=false
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from ..errors import ConfigurationMismatch, VersionConflict
from ..models import IdleConversationKey, freeze_object
from ..models import fingerprint as input_fingerprint
from .canonical import CanonicalRows, body, delta_payload
from .canonical_migration import CanonicalMigrationProgress
from .wire_json import strict

if TYPE_CHECKING:
    from .memory import MemoryIdleBackend


@dataclass
class MigrationStage:
    fingerprint: str
    copied: int = 0
    verified: int = 0


async def migrate(
    owner: MemoryIdleBackend,
    key: IdleConversationKey,
    *,
    component: str,
    source_component: Mapping[str, object],
    target_component: Mapping[str, object],
    ledger_delta: Mapping[str, object],
    absolute_expiry: Mapping[str, int],
    limit: int = 32,
    dry_run: bool = True,
) -> CanonicalMigrationProgress:
    if type(limit) is not int or not 1 <= limit <= 32 or type(dry_run) is not bool:
        raise ValueError("Canonical migration batch must be between 1 and 32")
    source = freeze_object(source_component, max_bytes=owner.config.max_components_bytes)
    target = freeze_object(target_component, max_bytes=owner.config.max_components_bytes)
    ledger_delta = freeze_object(ledger_delta, max_bytes=owner.config.max_components_bytes)
    absolute_expiry = dict(absolute_expiry)
    await owner.require_storage_format(3)
    async with owner.coordinator.hold(key), owner._lock:
        record = owner._records.get(key)
        if record is None:
            raise VersionConflict("Canonical migration source is missing")
        current = record.components.get(component)
        if current == target:
            return CanonicalMigrationProgress(0, 0, True, dry_run, False)
        if current != source:
            raise VersionConflict("Canonical migration source changed")
        desired = replace(record, components={**record.components, component: target})
        # Validate the complete envelope before installing rows or staging progress;
        # a target may fit individually while unrelated opaque components fill the
        # remaining conversation budget.
        freeze_object(desired.components, max_bytes=owner.config.max_components_bytes)
        revision, hot, identity = body(desired, component)
        if identity is None:
            raise ConfigurationMismatch("Canonical migration target has no identity")
        delta = delta_payload(
            ledger_delta, identity=identity, max_bytes=owner.config.max_components_bytes
        )
        if (
            delta["expected_revision"] is not None
            or delta["revision"] != revision
            or delta["hot"] != hot
            or delta["delete"]
            or delta["token_index_delete"]
        ):
            raise ConfigurationMismatch("Migration requires a complete initial canonical ledger")
        rows = dict(cast(Mapping[str, str], delta["put"]))
        indexes = dict(cast(Mapping[str, str], delta["token_index_put"]))
        if len(rows) > owner.config.max_receipts_per_conversation:
            raise ConfigurationMismatch("Increase capacity before preserving the legacy ledger")
        expiry = dict(absolute_expiry)
        for name, raw in rows.items():
            terminal = strict(raw)["status"] in {"completed", "failed"}
            deadline = expiry.get(name)
            if terminal != (deadline is not None) or (
                deadline is not None
                and (type(deadline) is not int or not 0 < deadline <= 2**53 - 1)
            ):
                raise ConfigurationMismatch("Original absolute receipt expiry must be preserved")
        if any(name not in rows for name in expiry) or any(
            name not in rows for name in indexes.values()
        ):
            raise ConfigurationMismatch("Canonical migration contains dangling evidence")
        fingerprint = input_fingerprint((source, target, delta, expiry))
        slot = (key, component)
        stage = owner._canonical_migrations.get(slot)
        if stage is not None and stage.fingerprint != fingerprint:
            raise VersionConflict("Canonical migration target changed")
        stage = stage or MigrationStage(fingerprint)
        total = len(rows)
        if dry_run:
            return CanonicalMigrationProgress(stage.copied, total, False, True, True)
        owner._canonical_migrations[slot] = stage
        if stage.copied < total:
            stage.copied = min(total, stage.copied + limit)
        else:
            stage.verified = min(total, stage.verified + limit)
        done = stage.copied == total and stage.verified == total
        if done:
            # The source, all immutable row bytes, absolute deadlines and ownership
            # were checked under this same task-scoped lock; no application callback.
            owner._canonical_rows[slot] = CanonicalRows(rows, expiry, indexes, set(rows))
            owner._save(desired)
            del owner._canonical_migrations[slot]
        return CanonicalMigrationProgress(stage.copied, total, done, False, True)
