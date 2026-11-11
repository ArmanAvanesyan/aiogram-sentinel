"""Explicit, effect-free migration of an integrated legacy navigation component."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol, cast

from aiogram_nav.clock import ManualClock
from aiogram_nav.codec import encode as navigation_identity
from aiogram_nav.models import ConversationKey
from aiogram_nav.storage.ledger_reducer import NavigationLedgerReducer

from ...errors import ConfigurationMismatch, SchemaUnsupported
from ...models import ActivitySnapshot, IdleConversationKey, IdleSnapshot
from ...storage.canonical_migration import CanonicalMigrationProgress
from ...storage.codec import decode, encode
from .codec import COMPONENT, component

if TYPE_CHECKING:
    from .repository import NavigationRepository


class MigrationHost(Protocol):
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
    ) -> CanonicalMigrationProgress: ...


async def migrate(
    repo: NavigationRepository,
    key: ConversationKey,
    *,
    limit: int = 32,
    dry_run: bool = True,
) -> CanonicalMigrationProgress:
    """Copy one page with original replay deadlines; perform no application effects.

    Drain old writers, activate format three, and migrate the Idle envelope first.
    Repeat until ``done``; keep the immutable source backup for administrative proof.
    """
    await repo.idle.initialize()
    if getattr(repo.idle.backend, "active_storage_format", 1) != 3:
        raise ConfigurationMismatch("Activate format three and migrate the Idle envelope first")
    idle_key = repo.mapping.to_idle(key)
    record = await repo.idle.backend.load(idle_key)
    value = component(record, expected_profile=repo.profile)
    if value is None or value.get("schema") == 3:
        return CanonicalMigrationProgress(0, 0, True, dry_run, False)
    assert record is not None  # nosec B101
    # Freeze the one-time projection at zero: crossing replay expiry while copying
    # must never alter the source operation set, proof count, or original deadline.
    reducer = NavigationLedgerReducer.from_legacy(
        key, str(value["ledger"]), clock=ManualClock(0), config=repo.config
    )
    receipts = value.get("activity_receipts", {})
    if not isinstance(receipts, Mapping):
        raise SchemaUnsupported("Malformed legacy first-activity receipt map")
    for operation_id, payload in cast(Mapping[object, object], receipts).items():
        if (
            not isinstance(operation_id, str)
            or not isinstance(payload, str)
            or not isinstance(decode(payload), ActivitySnapshot)
        ):
            raise SchemaUnsupported("Malformed original accepted activity result")
        reducer.set_integration_payload(operation_id, payload)
    delta = reducer.delta()
    target: dict[str, object] = {
        name: item
        for name, item in value.items()
        if name not in {"schema", "ledger", "activity_receipts"}
    }
    suspended = target.get("suspended_idle")
    if suspended is not None:
        if not isinstance(suspended, str) or not isinstance(
            decoded := decode(suspended), IdleSnapshot
        ):
            raise SchemaUnsupported("Malformed suspended idle recovery snapshot")
        if decoded.operation is not None:
            if record.idle.operation != decoded.operation:
                raise SchemaUnsupported(
                    "Resolve non-authoritative suspended operation before migration"
                )
            target["suspended_idle"] = encode(replace(decoded, operation=None), schema_version=3)
    target.update(
        schema=3,
        canonical=True,
        revision=delta.revision,
        hot=delta.hot,
        identity=navigation_identity(key),
    )
    return await cast(MigrationHost, repo.idle.backend).canonical_component_migrate(
        idle_key,
        component=COMPONENT,
        source_component=value,
        target_component=target,
        ledger_delta=delta.to_payload(),
        absolute_expiry=reducer.legacy_expiry,
        limit=limit,
        dry_run=dry_run,
    )
