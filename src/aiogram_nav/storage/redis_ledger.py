"""Bounded format-three reads and canonical ledger CAS without snapshot journals."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING, TypeVar, cast

from ..clock import ManualClock
from ..errors import OwnershipLost, PersistenceUnavailable, VersionConflict
from ..models import ConversationKey
from .ledger import LedgerDelta, LedgerRead, view_index
from .ledger_reducer import NavigationLedgerReducer
from .ledger_scripts import COMMIT, READ
from .memory import MemoryNavigationRepository
from .redis_transport import array, text
from .tokens import _known_tokens  # pyright: ignore[reportPrivateUsage]

T = TypeVar("T")

if TYPE_CHECKING:
    from .redis_store import RedisStore


def keys(store: RedisStore, key: ConversationKey) -> list[str]:
    base = store.keys(key)
    record = base[2]
    return [
        *base,
        f"{record}:operations",
        f"{record}:expiry",
        f"{record}:tokens",
        f"{record}:protected",
        f"{record}:index-count",
    ]


def operation_key(store: RedisStore, key: ConversationKey, operation_id: str) -> str:
    return f"{store.keys(key)[2]}:operation:{hashlib.sha256(operation_id.encode()).hexdigest()}"


def commit_metadata(store: RedisStore, key: ConversationKey, delta: object) -> tuple[str, str]:
    from .ledger import LedgerDelta

    if not isinstance(delta, LedgerDelta):
        raise ValueError("Expected a validated canonical ledger delta")
    rowkeys = {
        operation_id: operation_key(store, key, operation_id)
        for operation_id in set(delta.put) | set(delta.delete)
    }
    metadata: dict[str, str] = {}
    for operation_id, raw in delta.put.items():
        row = cast(dict[str, object], json.loads(raw))
        metadata[operation_id] = json.dumps(
            dict(
                key=rowkeys[operation_id],
                status="terminal" if row["status"] in ("completed", "failed") else "protected",
                index_fields=sorted(
                    field for field, owner in delta.token_index_put.items() if owner == operation_id
                ),
            ),
            separators=(",", ":"),
        )
    return json.dumps(rowkeys), json.dumps(metadata)


def _pairs(raw: object) -> dict[str, str]:
    values = array(raw)
    if len(values) % 2:
        raise PersistenceUnavailable("Canonical ledger rows are inconsistent")
    return {text(values[i]): text(values[i + 1]) for i in range(0, len(values), 2)}


async def read(
    store: RedisStore,
    key: ConversationKey,
    *,
    operation_id: str = "",
    token: str = "",
    reservation_id: str = "",
    view_id: str = "",
    _migration_attempts: int = 0,
    _selected_session: str | None = None,
) -> tuple[str, NavigationLedgerReducer]:
    if view_id and _selected_session is None:
        raw, initial = await read(
            store,
            key,
            operation_id=operation_id,
            token=token,
            reservation_id=reservation_id,
            _migration_attempts=_migration_attempts,
        )
        session = initial.session_id
        if session is None:
            return raw, initial
        raw, selected = await read(
            store,
            key,
            operation_id=operation_id,
            token=token,
            reservation_id=reservation_id,
            view_id=view_id,
            _selected_session=session,
            _migration_attempts=_migration_attempts,
        )
        if selected.session_id != session:
            raise VersionConflict("Navigation session changed during view-index preselection")
        return raw, selected
    required_indexes = (
        ([f"t:{token}"] if token else [])
        + ([f"o:{reservation_id}"] if reservation_id else [])
        + (
            [view_index(view_id, _selected_session)]
            if view_id and _selected_session is not None
            else []
        )
    )
    response = array(
        await store.connection.script(
            READ,
            keys(store, key),
            [
                store.profile,
                store.history,
                store.member(key),
                operation_id,
                token,
                reservation_id,
                json.dumps(
                    [view_index(view_id, _selected_session)]
                    if view_id and _selected_session is not None
                    else []
                ),
            ],
            mutation=False,
        )
    )
    if text(response[0]) == "legacy":
        if _migration_attempts >= 16:
            raise VersionConflict("Canonical migration contention limit reached")
        await migrate_record(
            store,
            key,
            text(response[1]),
            int(text(response[2])) * 1000 + int(text(response[3])) // 1000,
        )
        return await read(
            store,
            key,
            operation_id=operation_id,
            token=token,
            reservation_id=reservation_id,
            view_id=view_id,
            _migration_attempts=_migration_attempts + 1,
            _selected_session=_selected_session,
        )
    if text(response[0]) != "ok":
        raise PersistenceUnavailable("Canonical ledger history is absent or inconsistent")
    hot = text(response[1])
    now = int(text(response[3])) * 1000 + int(text(response[4])) // 1000
    store.clock.update(now)
    rows = _pairs(response[5])
    for operation_id, raw_metadata in _pairs(response[8]).items():
        metadata = cast(dict[str, object], json.loads(raw_metadata))
        if metadata.get("key") != operation_key(store, key, operation_id):
            raise PersistenceUnavailable("Canonical operation key identity mismatch")
    expiry = {name: int(float(value)) for name, value in _pairs(response[6]).items()}
    revision: str | None = None
    if hot:
        # Strict decoder validates the entire hot/operation contract below.
        body = cast(dict[str, object], json.loads(hot))
        revision = cast(str, body["revision"])
    snapshot = LedgerRead(
        revision,
        hot or None,
        rows,
        int(response[2]) if type(response[2]) is int else int(text(response[2])),
        expiry,
        tuple(text(value) for value in array(response[7])),
        indexes={field: owner or None for field, owner in _pairs(response[9]).items()},
    )
    return hot, NavigationLedgerReducer(
        key,
        snapshot,
        clock=ManualClock(now),
        config=store.config,
        required_indexes=required_indexes,
    )


async def commit_delta(
    store: RedisStore,
    key: ConversationKey,
    raw: str,
    delta: LedgerDelta,
    *,
    scope: object | None = None,
    expires: int = 0,
    migration_expiry: dict[str, int] | None = None,
    migration_operation_id: str = "",
) -> str:
    if scope is not None and not store.coordinator.scope_matches(key, scope):
        raise OwnershipLost("Canonical ledger coordination scope expired")
    fence = store.coordinator.fencing(key, scope=scope)
    rowkeys, metadata = commit_metadata(store, key, delta)
    response = await store.connection.script(
        COMMIT,
        [
            *keys(store, key),
            fence[0] if fence else f"{store.prefix}:unused-lock",
            f"{store.prefix}:storage-format",
        ],
        [
            store.profile,
            store.history,
            store.member(key),
            raw,
            json.dumps(delta.to_payload()),
            store.config.max_conversations,
            fence[1] if fence else "",
            expires,
            store.config.max_receipts,
            rowkeys,
            metadata,
            json.dumps(migration_expiry or {}),
            migration_operation_id,
        ],
    )
    return text(response)


async def migrate_record(store: RedisStore, key: ConversationKey, raw: str, now: int) -> None:
    if store.storage_format != 3:
        raise PersistenceUnavailable("Explicit storage format 3 activation is required")
    manifest_raw = await store.connection.call("GET", f"{store.prefix}:storage-format")
    manifest = cast(dict[str, object], json.loads(text(manifest_raw)))
    if manifest.get("format") != 3 or type(manifest.get("operation_id")) is not str:
        raise PersistenceUnavailable("Canonical storage activation proof is missing")
    projection = await asyncio.to_thread(
        NavigationLedgerReducer.from_legacy,
        key,
        raw,
        clock=ManualClock(now),
        config=store.config,
    )
    status = await commit_delta(
        store,
        key,
        raw,
        projection.delta(),
        migration_expiry=projection.legacy_expiry,
        migration_operation_id=cast(str, manifest["operation_id"]),
    )
    if status not in ("ok", "retry"):
        raise PersistenceUnavailable("Canonical record migration failed its atomic preconditions")


async def apply(
    store: RedisStore,
    key: ConversationKey,
    callback: Callable[[MemoryNavigationRepository], Awaitable[T]],
    *,
    scope: object | None = None,
    deadline: Callable[[T], int] | None = None,
    prune: bool = False,
    operation_id: str = "",
    token: str = "",
    reservation_id: str = "",
    view_id: str = "",
) -> T:
    """Execute a pure bounded reducer then atomically persist its canonical delta."""
    from ..errors import Overloaded, SessionExpired
    from ..models import NavigationToken, PreparedAction

    for _ in range(16):
        raw, projection = await read(
            store,
            key,
            operation_id=operation_id,
            token=token,
            reservation_id=reservation_id,
            view_id=view_id,
        )
        memory = projection.repository
        if scope is not None and not store.coordinator.scope_matches(key, scope):
            raise OwnershipLost("Canonical ledger coordination scope expired")
        original = memory._records.get(key)  # pyright: ignore[reportPrivateUsage]
        previous_entry = original.operations.get(operation_id) if original is not None else None
        previous = previous_entry.prepared if previous_entry is not None else None
        previous_tokens = (
            {entry.token.token: replace(entry) for entry in _known_tokens(original)}
            if original is not None
            else {}
        )
        result = await callback(memory)
        record = memory._records.get(key)  # pyright: ignore[reportPrivateUsage]
        if prune and record is not None and memory._removable(record):  # pyright: ignore[reportPrivateUsage]
            del memory._records[key]  # pyright: ignore[reportPrivateUsage]
        delta = projection.delta()
        expires = (
            deadline(result) if deadline is not None and (delta.hot != raw or delta.put) else 0
        )
        if isinstance(result, PreparedAction) and previous == result:
            expires = 0
        if isinstance(result, NavigationToken) and record is not None:
            current_token = next(
                (entry for entry in _known_tokens(record) if entry.token.token == result.token),
                None,
            )
            if current_token is not None and previous_tokens.get(result.token) == current_token:
                expires = 0
        status = await commit_delta(store, key, raw, delta, scope=scope, expires=expires)
        if status == "ok":
            return result
        if status == "retry":
            continue
        if status in ("capacity", "receipts"):
            raise Overloaded(
                "Canonical ledger capacity exhausted; expired evidence must be reclaimed"
            )
        if status == "ownership":
            raise OwnershipLost("Canonical ledger conversation lease expired")
        if status == "expired":
            raise SessionExpired("Navigation authorization expired before canonical commit")
        raise PersistenceUnavailable("Canonical ledger failed its atomic storage preconditions")
    raise VersionConflict("Canonical ledger contention/migration retry limit reached")
