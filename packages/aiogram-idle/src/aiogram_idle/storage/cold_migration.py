"""Staged format-two migration, preserving original results and an immutable backup."""

from __future__ import annotations

# A private, exclusively coordinated Engine is the shared audited domain decoder.
# pyright: reportPrivateUsage=false
import hashlib
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ..errors import BackendInconsistent, ConfigurationMismatch, OwnershipLost, VersionConflict
from ..models import IdleConversationKey, Phase, RuntimeSnapshot
from .codec import encode
from .cold import (
    MAX_EXACT_MILLISECONDS,
    ColdState,
    hot_payload,
    keys,
    receipt_key,
    receipt_prefix,
    result_prefix,
)
from .cold_migration_scripts import COPY
from .redis_transport import text
from .state import OperationReceipt
from .wire_json import compact

if TYPE_CHECKING:
    from .redis_store import RedisStore

MAX_SOURCE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class MigrationProgress:
    """Copied counts processed identities, including already-expired source entries."""

    copied: int
    total: int
    done: bool
    dry_run: bool
    legacy: bool
    backup_key: str | None = None
    source_digest: str | None = None
    backup_bytes: int = 0
    staged_bytes: int = 0
    protected_backup: bool = False


def migration_key(store: RedisStore, key: IdleConversationKey) -> str:
    return f"{store.prefix}:cold-migration:{store.ident(key)}"


def backup_keys(store: RedisStore, key: IdleConversationKey) -> tuple[str, str]:
    suffix = store.ident(key)
    return (
        f"{store.prefix}:cold-migration-source:{suffix}",
        f"{store.prefix}:cold-migration-proof:{suffix}",
    )


def _absolute_expiry(receipt: OperationReceipt[object]) -> int:
    milliseconds = receipt.expires_at * 1000
    if not math.isfinite(milliseconds) or not 0 < milliseconds <= MAX_EXACT_MILLISECONDS:
        raise ConfigurationMismatch("Original replay expiry exceeds exact Redis millisecond range")
    return math.ceil(milliseconds)


def _protected(record: RuntimeSnapshot) -> bool:
    # Core knows no replay lifetime for an opaque component. Only its owner can
    # attest preservation/resolution; never infer safety from a private Nav shape.
    opaque = any(name != "__external_session__" for name in record.components)
    return (
        record.idle.operation is not None
        or record.idle.phase in {Phase.EFFECT_UNKNOWN, Phase.QUARANTINED}
        or opaque
    )


def source_summary(raw: str) -> tuple[RuntimeSnapshot, dict[str, OperationReceipt[object]], int]:
    from .codec import decode

    state = decode(raw)
    if not isinstance(state, dict):
        raise BackendInconsistent("Migration source domain state is malformed")
    fields = cast(dict[str, object], state)
    record, receipts = fields.get("record"), fields.get("receipts")
    if not isinstance(record, RuntimeSnapshot) or not isinstance(receipts, dict):
        raise BackendInconsistent("Migration source evidence is malformed")
    values = cast(dict[str, OperationReceipt[object]], receipts)
    if any(
        not isinstance(value, OperationReceipt)
        for value in cast(dict[str, object], receipts).values()
    ):
        raise BackendInconsistent("Migration source replay evidence is malformed")
    maximum = max((_absolute_expiry(value) for value in values.values()), default=1)
    return record, values, maximum


def _row(
    store: RedisStore,
    key: IdleConversationKey,
    operation_id: str,
    receipt: OperationReceipt[object],
) -> dict[str, object]:
    result = encode(receipt.result, schema_version=3)
    reference = (
        hashlib.sha256(result.encode()).hexdigest()
        if isinstance(receipt.result, RuntimeSnapshot)
        else None
    )
    row = compact(
        {
            "schema_version": 3,
            "key": store.member(key),
            "operation_id": operation_id,
            "fingerprint": receipt.fingerprint,
            "expires_at": _absolute_expiry(receipt),
            "result": None if reference else result,
            "result_ref": reference,
        }
    )
    return {
        "id": operation_id,
        "row_key": receipt_key(store, key, operation_id),
        "blob_key": result_prefix(store, key) + (reference or "unused"),
        "row": row,
        "blob": result if reference else "",
        "expiry": _absolute_expiry(receipt),
    }


async def _position(store: RedisStore, key: IdleConversationKey, digest: str, total: int) -> int:
    raw = await store.connection.call("HGETALL", migration_key(store, key))
    if not isinstance(raw, dict):
        raise BackendInconsistent("Malformed staged migration progress")
    values = {text(name): text(value) for name, value in cast(dict[object, object], raw).items()}
    if not values:
        return 0
    if set(values) != {"source", "position", "total", "key"}:
        raise BackendInconsistent("Malformed staged migration progress")
    if values["key"] != store.member(key):
        raise BackendInconsistent("Migration progress belongs to another conversation")
    if values["source"] != digest:
        raise VersionConflict("Migration source changed; inspect the retained source backup")
    try:
        position, previous_total = int(values["position"]), int(values["total"])
    except ValueError as error:
        raise BackendInconsistent("Malformed staged migration position") from error
    if previous_total != total or not 0 <= position <= total:
        raise BackendInconsistent("Migration progress does not match its source")
    return position


async def _page(
    store: RedisStore, key: IdleConversationKey, *, limit: int, dry_run: bool
) -> MigrationProgress:
    engine, source, config = await store.read(key)
    context = engine.cold_state
    if not isinstance(context, ColdState):
        raise BackendInconsistent("Missing migration source observation")
    if not context.legacy:
        return MigrationProgress(0, 0, True, dry_run, False)
    size = len(source.encode())
    if size > MAX_SOURCE_BYTES:
        raise ConfigurationMismatch("Migration source backup exceeds the explicit 32 MiB bound")
    record = engine._records.get(key)
    if record is None:
        raise BackendInconsistent("Legacy migration source has no authoritative runtime")
    digest = hashlib.sha256(source.encode()).hexdigest()
    receipts = engine._receipts.items.get(key, {})
    for name, receipt in receipts.items():
        for value in (name, receipt.fingerprint):
            if type(value) is not str or not 1 <= len(value) <= 256:
                raise BackendInconsistent("Legacy replay identity is malformed")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise BackendInconsistent("Legacy replay identity is not valid UTF-8") from error
    names = sorted(receipts)
    position = await _position(store, key, digest, len(names))
    selected = names[position : position + limit]
    next_position = position + len(selected)
    current_ms = math.floor(store.clock.now() * 1000)
    original_maximum = max((_absolute_expiry(receipt) for receipt in receipts.values()), default=1)
    protected = _protected(record)
    retained = [
        _row(store, key, operation_id, receipts[operation_id])
        for operation_id in selected
        if _absolute_expiry(receipts[operation_id]) > current_ms
    ]
    backup, proof_key = backup_keys(store, key)
    proof = compact(
        {
            "schema_version": 3,
            "kind": "idle-migration-source",
            "history": store.history,
            "key": store.member(key),
            "source_sha256": digest,
            "bytes": size,
            "protected": protected,
            "original_replay_until": original_maximum,
            "expires_at": None if protected else original_maximum,
        }
    )
    staged = sum(
        len(cast(str, row["row"]).encode()) + len(cast(str, row["blob"]).encode())
        for row in retained
    )
    report = MigrationProgress(
        next_position,
        len(names),
        next_position == len(names),
        dry_run,
        True,
        backup,
        digest,
        size,
        staged,
        protected,
    )
    if dry_run:
        return report
    fence = store.fencer(key)
    if fence is None:
        raise ConfigurationMismatch(
            "Migration must hold the backend's verified conversation coordinator"
        )
    hot, pending = hot_payload(engine)
    base = store.keys(key)
    cold = keys(store, key)
    result = text(
        await store.connection.script(
            COPY,
            [
                base[0],
                base[1],
                base[4],
                store.prefix + ":created",
                store.prefix + ":config-established",
                store.prefix + ":parked",
                migration_key(store, key),
                cold[0],
                cold[1],
                cold[2],
                store.prefix + ":receipt-sweep",
                backup,
                proof_key,
                fence[0],
                *(cast(str, row[name]) for row in retained for name in ("row_key", "blob_key")),
            ],
            [
                source,
                engine.original_job,
                config,
                store.history,
                store.member(key),
                digest,
                position,
                next_position,
                len(names),
                compact(retained),
                hot,
                pending,
                int(report.done),
                receipt_prefix(store, key),
                result_prefix(store, key),
                proof,
                0 if protected else original_maximum,
                fence[1],
            ],
        )
    )
    if result == "ownership":
        raise OwnershipLost("Migration conversation ownership ended")
    if result in {"active", "parked"}:
        raise ConfigurationMismatch("Drain active claims and resolve parked state before migration")
    if result != "ok":
        raise VersionConflict("Migration source, position, job or configuration changed")
    return report


async def migrate(
    store: RedisStore, key: IdleConversationKey, *, limit: int = 32, dry_run: bool = True
) -> MigrationProgress:
    """Copy one bounded page under shared coordination; never run application effects."""
    if type(limit) is not int or not 1 <= limit <= 1000 or type(dry_run) is not bool:
        raise ValueError("Migration page limit must be between 1 and 1000")
    await store.initialize()
    if store.format_version != 3:
        raise ConfigurationMismatch("Activate storage format three after draining old writers")
    if dry_run:
        return await _page(store, key, limit=limit, dry_run=True)
    scope = store.migration_scope
    if scope is None:
        raise ConfigurationMismatch("Migration requires the backend's verified coordinator scope")
    async with scope(key):
        return await _page(store, key, limit=limit, dry_run=False)
