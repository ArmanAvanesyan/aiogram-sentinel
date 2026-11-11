"""Bounded, fenced conversion from an opaque legacy component to canonical rows."""

from __future__ import annotations

# Backend-owned scratch engines never escape the storage boundary.
# pyright: reportPrivateUsage=false
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from ..errors import BackendInconsistent, ConfigurationMismatch, OwnershipLost, VersionConflict
from ..models import IdleConversationKey, fingerprint, freeze_object, validate_unicode
from .canonical import body, delta_payload
from .canonical_migration_scripts import COPY
from .canonical_redis import component_prefix, row_key
from .cold import MAX_EXACT_MILLISECONDS, ColdState, hot_payload
from .cold_backup import export_backup, inspect_backup
from .cold_migration import source_summary
from .redis_transport import text
from .wire_json import compact, strict

if TYPE_CHECKING:
    from .redis_store import RedisStore


@dataclass(frozen=True)
class CanonicalMigrationProgress:
    copied: int
    total: int
    done: bool
    dry_run: bool
    legacy: bool
    source_digest: str | None = None
    verified: int = 0
    phase: str = "copy"


def migration_key(store: RedisStore, key: IdleConversationKey, component: str) -> str:
    return component_prefix(store, key, component) + ":migration"


async def _page(
    store: RedisStore,
    key: IdleConversationKey,
    *,
    component: str,
    source_component: Mapping[str, object],
    target_component: Mapping[str, object],
    ledger_delta: Mapping[str, object],
    absolute_expiry: Mapping[str, int],
    limit: int,
    dry_run: bool,
) -> CanonicalMigrationProgress:
    engine, source, config = await store.read(key)
    if not isinstance(engine.cold_state, ColdState) or engine.cold_state.legacy:
        raise ConfigurationMismatch("Migrate the Idle envelope before its opaque components")
    record = engine._records.get(key)
    if record is None:
        raise BackendInconsistent("Canonical migration source runtime is missing")
    current = record.components.get(component)
    if isinstance(current, Mapping) and current.get("canonical") is True:
        if current != freeze_object(target_component):
            raise VersionConflict("Canonical component already has a different target")
        return CanonicalMigrationProgress(0, 0, True, dry_run, False)
    if current != freeze_object(source_component):
        raise VersionConflict("Legacy component changed before migration")
    target = replace(
        record,
        components=freeze_object({**record.components, component: target_component}),
        store_version=record.store_version + 1,
    )
    revision, hot, identity = body(target, component)
    assert identity is not None  # nosec B101
    delta = delta_payload(
        ledger_delta, identity=identity, max_bytes=store.config.max_components_bytes
    )
    if (
        delta["expected_revision"] is not None
        or delta["revision"] != revision
        or delta["hot"] != hot
        or delta["delete"]
        or delta["token_index_delete"]
    ):
        raise ConfigurationMismatch("Canonical migration requires one complete initial ledger")
    rows = cast(dict[str, str], delta["put"])
    indexes = cast(dict[str, str], delta["token_index_put"])
    if len(rows) > store.config.max_receipts_per_conversation:
        raise ConfigurationMismatch("Increase receipt capacity before preserving the legacy ledger")
    for name, raw in rows.items():
        terminal = strict(raw)["status"] in ("completed", "failed")
        expiry = absolute_expiry.get(name)
        if terminal != (expiry is not None) or (
            expiry is not None
            and (type(expiry) is not int or not 0 < expiry <= MAX_EXACT_MILLISECONDS)
        ):
            raise ConfigurationMismatch("Preserve every original terminal absolute expiry")
    if any(name not in rows for name in absolute_expiry) or any(
        owner not in rows for owner in indexes.values()
    ):
        raise ConfigurationMismatch("Migration contains dangling receipt/index evidence")
    backup = await inspect_backup(store, key)
    if backup is None or not backup.protected:
        raise ConfigurationMismatch(
            "Canonical migration requires its immutable protected Idle source backup"
        )
    original = await export_backup(store, key, expected_digest=backup.source_digest)
    source_record, _, _ = source_summary(original)
    if source_record.components.get(component) != freeze_object(source_component):
        raise VersionConflict("The immutable backup does not prove this legacy component")
    digest = fingerprint(source_component)
    target_digest = fingerprint(
        {"component": target_component, "delta": delta, "expiry": absolute_expiry}
    )
    progress_raw = await store.connection.call("HGETALL", migration_key(store, key, component))
    if not isinstance(progress_raw, dict):
        raise BackendInconsistent("Invalid canonical migration progress")
    progress = {text(k): text(v) for k, v in cast(dict[object, object], progress_raw).items()}
    position = verified = pages = 0
    chain = ""
    if progress:
        proof_names = {name for name in progress if name.startswith("proof:")}
        if (
            set(progress)
            != {"source", "target", "position", "total", "key", "verified", "pages", "chain"}
            | proof_names
            or progress["source"] != digest
            or progress["target"] != target_digest
            or progress["key"] != store.member(key)
        ):
            raise VersionConflict("Canonical migration source or target changed")
        try:
            position = int(progress["position"])
            total = int(progress["total"])
            verified = int(progress["verified"])
            pages = int(progress["pages"])
            proof_positions = sorted(int(name[6:]) for name in proof_names)
            if any(name != "proof:" + str(int(name[6:])) for name in proof_names):
                raise ValueError("Noncanonical proof position")
        except ValueError as error:
            raise BackendInconsistent("Invalid canonical migration position") from error
        if (
            not 0 <= verified <= position <= total
            or total != len(rows)
            or len(proof_names) != pages
            or (proof_positions and (proof_positions[0] <= 0 or proof_positions[-1] != verified))
            or (verified > 0 and not proof_positions)
        ):
            raise BackendInconsistent("Canonical migration count proof changed")
        for endpoint in proof_positions:
            proof = progress["proof:" + str(endpoint)]
            if len(proof) != 64 or any(ch not in "0123456789abcdef" for ch in proof):
                raise BackendInconsistent("Canonical migration page proof changed")
            chain = hashlib.sha1((chain + proof).encode(), usedforsecurity=False).hexdigest()
        if chain != progress["chain"]:
            raise BackendInconsistent("Canonical migration verification chain changed")
    names = sorted(rows)
    verifying = position == len(names)
    cursor = verified if verifying else position
    selected = names[cursor : cursor + limit]
    following = position if verifying else position + len(selected)
    next_verified = verified + len(selected) if verifying else 0
    result = CanonicalMigrationProgress(
        following,
        len(names),
        verifying and next_verified == len(names),
        dry_run,
        True,
        digest,
        next_verified,
        "verify" if verifying else "copy",
    )
    if dry_run:
        return result
    fence = store.fencer(key)
    if fence is None:
        raise ConfigurationMismatch("Canonical migration requires verified conversation ownership")
    prefix = component_prefix(store, key, component)
    selected_rows: list[dict[str, object]] = []
    for name in selected:
        terminal = name in absolute_expiry
        owned = {field: owner for field, owner in indexes.items() if owner == name}
        physical = row_key(prefix, name)
        selected_rows.append(
            {
                "id": name,
                "key": physical,
                "row": rows[name],
                "expiry": absolute_expiry.get(name, 0),
                "metadata": compact(
                    {
                        "key": physical,
                        "status": "terminal" if terminal else "protected",
                        "index_fields": sorted(owned),
                    }
                ),
                "indexes": owned,
            }
        )
    engine._records[key] = target
    target_hot, _ = hot_payload(engine)
    from .cold_migration import backup_keys

    backup_key, proof_key = backup_keys(store, key)
    raw_proof = text(await store.connection.call("GET", proof_key))
    base = store.keys(key)
    status = text(
        await store.connection.script(
            COPY,
            [
                base[0],
                base[1],
                base[4],
                store.prefix + ":created",
                store.prefix + ":config-established",
                store.prefix + ":parked",
                fence[0],
                migration_key(store, key, component),
                prefix + ":metadata",
                prefix + ":expiry",
                prefix + ":indexes",
                prefix + ":protected",
                prefix + ":index-count",
                store.prefix + ":component-sweep",
                backup_key,
                proof_key,
                *(cast(str, item["key"]) for item in selected_rows),
            ],
            [
                source,
                engine.original_job,
                config,
                store.history,
                store.member(key),
                fence[1],
                digest,
                position,
                following,
                len(names),
                compact(selected_rows),
                target_hot,
                int(result.done),
                prefix,
                compact({"key": store.member(key), "component": component}),
                original,
                raw_proof,
                target_digest,
                identity,
                "verify" if verifying else "copy",
                verified,
                next_verified,
                pages,
                chain,
                hashlib.sha256(compact(selected_rows).encode()).hexdigest(),
            ],
        )
    )
    if status == "ownership":
        raise OwnershipLost("Canonical migration ownership expired")
    if status in ("active", "parked"):
        raise ConfigurationMismatch(
            "Drain claimed jobs and resolve parked evidence before migration"
        )
    if status != "ok":
        raise VersionConflict("Canonical migration source, job, config or page changed")
    return result


async def migrate(
    store: RedisStore,
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
    """Preserve source and original replay lifetimes until a fenced final cutover."""
    if type(limit) is not int or not 1 <= limit <= 1000 or type(dry_run) is not bool:
        raise ValueError("Invalid bounded canonical migration page")
    if not isinstance(cast(object, component), str) or not component or len(component) > 128:
        raise ConfigurationMismatch("Component name must be a bounded nonempty identifier")
    validate_unicode(component, "canonical migration component")
    # Freeze all caller-owned mappings before the first suspension. Source and
    # target fingerprints must describe the same inputs throughout both passes.
    source_component = freeze_object(source_component, max_bytes=store.config.max_components_bytes)
    target_component = freeze_object(target_component, max_bytes=store.config.max_components_bytes)
    ledger_delta = freeze_object(ledger_delta, max_bytes=store.config.max_components_bytes)
    absolute_expiry = dict(absolute_expiry)
    await store.initialize()
    if store.format_version != 3:
        raise ConfigurationMismatch("Activate format three before canonical component migration")
    if dry_run:
        return await _page(
            store,
            key,
            component=component,
            source_component=source_component,
            target_component=target_component,
            ledger_delta=ledger_delta,
            absolute_expiry=absolute_expiry,
            limit=limit,
            dry_run=True,
        )
    if store.migration_scope is None:
        raise ConfigurationMismatch("Canonical migration requires verified shared coordination")
    async with store.migration_scope(key):
        return await _page(
            store,
            key,
            component=component,
            source_component=source_component,
            target_component=target_component,
            ledger_delta=ledger_delta,
            absolute_expiry=absolute_expiry,
            limit=limit,
            dry_run=False,
        )
