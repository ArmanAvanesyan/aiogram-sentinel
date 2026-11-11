"""Opaque canonical component rows, atomically owned by the activity backend."""

from __future__ import annotations

# Canonical hosts persist opaque validated JSON; no navigation dependency exists.
# pyright: reportPrivateUsage=false
from collections.abc import Mapping
from copy import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ..errors import (
    ActivityConflict,
    BackendInconsistent,
    ConfigurationError,
    Overloaded,
    OwnershipLost,
    VersionConflict,
)
from ..models import IdleConversationKey, RuntimeSnapshot, validate_unicode
from ..policies import IdlePolicy
from .component_transaction import ownership
from .coordination import check_manifest
from .receipts import fingerprint
from .state import Claim
from .wire_json import compact, strict

if TYPE_CHECKING:
    from .memory import MemoryIdleBackend


@dataclass
class CanonicalRows:
    rows: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    expiry: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    indexes: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    known_ids: set[str] = field(default_factory=lambda: set[str]())
    unloaded_count: int = 0

    def __post_init__(self) -> None:
        self.known_ids.update(self.rows)


def body(
    record: RuntimeSnapshot | None, component: str
) -> tuple[str | None, str | None, str | None]:
    value = record.components.get(component) if record else None
    if value is None:
        return None, None, None
    if not isinstance(value, Mapping) or value.get("canonical") is not True:
        raise ConfigurationError("Migrate the legacy component before canonical operations")
    revision, hot, identity = value.get("revision"), value.get("hot"), value.get("identity")
    if (
        not isinstance(revision, str)
        or not revision
        or (hot is not None and not isinstance(hot, str))
        or not isinstance(identity, str)
        or not identity
    ):
        raise BackendInconsistent("Malformed canonical component reference")
    if hot:
        parsed = strict(hot)
        if (
            parsed.get("revision") != revision
            or parsed.get("schema_version") != 3
            or parsed.get("kind") != "hot"
        ):
            raise BackendInconsistent("Canonical component revision changed")
    return revision, hot, identity


def names(value: object, *, limit: int = 256) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ConfigurationError("Canonical operation names must be bounded strings")
    items = cast(list[object] | tuple[object, ...], value)
    if any(not isinstance(item, str) or not item or len(item) > limit for item in items):
        raise ConfigurationError("Canonical operation names must be bounded strings")
    named = tuple(cast(str, item) for item in items)
    if len(set(named)) != len(named):
        raise ConfigurationError("Canonical operation names must be unique")
    for name in named:
        validate_unicode(name, "canonical operation name")
    return named


def strings(
    value: object, *, key_limit: int = 256, value_limit: int | None = None
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ConfigurationError("Canonical row maps are required")
    result: dict[str, str] = {}
    for key, item in cast(Mapping[object, object], value).items():
        if not isinstance(key, str) or not key or len(key) > key_limit or not isinstance(item, str):
            raise ConfigurationError("Canonical row fields must be bounded named strings")
        if value_limit is not None and len(item) > value_limit:
            raise ConfigurationError("Canonical index owner exceeds its operation ID bound")
        validate_unicode(key, "canonical field name")
        result[key] = item
    return result


def delta_payload(
    value: Mapping[str, object], *, identity: str, max_bytes: int
) -> dict[str, object]:
    expected = {
        "expected_revision",
        "revision",
        "hot",
        "put",
        "delete",
        "terminal_retention_ms",
        "token_index_put",
        "token_index_delete",
    }
    if (
        set(value) != expected
        or not isinstance(value["revision"], str)
        or not value["revision"]
        or (
            value["expected_revision"] is not None
            and not isinstance(value["expected_revision"], str)
        )
    ):
        raise ConfigurationError("Malformed canonical delta revision")
    hot = value["hot"]
    if hot is not None and not isinstance(hot, str):
        raise ConfigurationError("Malformed canonical hot state")
    put = strings(value["put"])
    delete = names(value["delete"])
    indexes = strings(value["token_index_put"], key_limit=258, value_limit=256)
    index_delete = names(value["token_index_delete"], limit=258)
    duration = value["terminal_retention_ms"]
    if not isinstance(duration, Mapping) or any(
        not isinstance(key, str) or key not in put or type(item) is not int or item <= 0
        for key, item in cast(Mapping[object, object], duration).items()
    ):
        raise ConfigurationError("Terminal rows require positive retention durations")
    expiry = {
        cast(str, key): cast(int, item)
        for key, item in cast(Mapping[object, object], duration).items()
    }
    for operation_id, raw in put.items():
        row = strict(raw)
        status = row.get("status")
        if (
            row.get("schema_version") != 3
            or row.get("kind") != "operation"
            or row.get("id") != operation_id
            or row.get("conversation") != identity
            or status not in {"prepared", "unknown", "completed", "failed"}
        ):
            raise ConfigurationError("Canonical row identity changed")
        terminal = status in {"completed", "failed"}
        if not terminal and operation_id in expiry:
            raise ConfigurationError("Pending or unknown evidence cannot receive terminal TTL")
    payload: dict[str, object] = {
        **value,
        "put": put,
        "delete": delete,
        "terminal_retention_ms": expiry,
        "token_index_put": indexes,
        "token_index_delete": index_delete,
    }

    if len(compact(payload).encode()) > max_bytes:
        raise Overloaded("Canonical delta exceeds the byte budget", reason="bytes", limit=max_bytes)
    return payload


def observe(
    rows: CanonicalRows,
    revision: str | None,
    hot: str | None,
    *,
    now_ms: int,
    operation_id: str = "",
    token: str = "",
    reservation_id: str = "",
    index_keys: tuple[str, ...] = (),
) -> dict[str, object]:
    expired = tuple(name for name, expiry in rows.expiry.items() if expiry <= now_ms)[:32]
    wanted: set[str] = {operation_id} if operation_id else set()
    protected: set[str] = set()
    required: set[str] = set()
    if hot:
        value = strict(hot)
        for name in ("current_owner", "pending_id"):
            pointer = value.get(name)
            if pointer is not None:
                if not isinstance(pointer, str):
                    raise BackendInconsistent("Malformed canonical owner reference")
                wanted.add(pointer)
                required.add(pointer)
                if name == "pending_id":
                    protected.add(pointer)
    for index in (
        ("t:" + token) if token else "",
        ("o:" + reservation_id) if reservation_id else "",
    ):
        if index and index in rows.indexes:
            wanted.add(rows.indexes[index])
            required.add(rows.indexes[index])
    selected_indexes: dict[str, str | None] = {}
    for index in index_keys:
        selected_indexes[index] = rows.indexes.get(index)
        if selected_indexes[index] is not None:
            wanted.add(cast(str, selected_indexes[index]))
            required.add(cast(str, selected_indexes[index]))
    wanted.update(expired)
    expired_ids = list(expired)
    selected: dict[str, str] = {}
    expiry: dict[str, int] = {}
    for name in wanted:
        until = rows.expiry.get(name)
        raw = rows.rows.get(name)
        if raw is None:
            if (
                name in protected
                or (name in required and (until is None or until > now_ms))
                or (until is not None and until > now_ms)
            ):
                raise BackendInconsistent("Promised canonical row is missing")
        elif until is None or until > now_ms:
            selected[name] = raw
        if until is not None:
            expiry[name] = until
            if until <= now_ms and name not in expired_ids:
                expired_ids.append(name)
    return {
        "revision": revision,
        "hot": hot,
        "operations": selected,
        "retained_count": len(rows.known_ids) + rows.unloaded_count,
        "operation_expiry": expiry,
        "expired": expired_ids,
        "indexes": selected_indexes,
    }


def apply_rows(
    previous: CanonicalRows, delta: Mapping[str, object], *, now_ms: int, limit: int
) -> CanonicalRows:
    rows = CanonicalRows(
        dict(previous.rows),
        dict(previous.expiry),
        dict(previous.indexes),
        set(previous.known_ids),
        previous.unloaded_count,
    )
    deletion = names(delta["delete"])
    for name in deletion:
        if name in rows.known_ids and rows.expiry.get(name, now_ms + 1) > now_ms:
            raise ConfigurationError("Unexpired replay and unresolved evidence are protected")
    for name in deletion:
        rows.rows.pop(name, None)
        rows.known_ids.discard(name)
        rows.expiry.pop(name, None)
    put = strings(delta["put"])
    duration = cast(Mapping[str, int], delta["terminal_retention_ms"])
    if len(rows.known_ids | set(put)) + rows.unloaded_count > limit:
        raise Overloaded(
            "Canonical operation capacity is exhausted",
            reason="replay_slots",
            limit=limit,
            used=len(rows.rows),
        )
    for name, raw in put.items():
        # Rewriting terminal evidence does not renew its promised window.
        existing_expiry = rows.expiry.get(name)
        rows.rows[name] = raw
        rows.known_ids.add(name)
        status = strict(raw).get("status")
        if status in {"completed", "failed"}:
            if existing_expiry is None and name not in duration:
                raise ConfigurationError("New terminal evidence requires retention duration")
            deadline = existing_expiry if existing_expiry is not None else now_ms + duration[name]
            if deadline > 9_007_199_254_740_991 or deadline < 0:
                raise ConfigurationError(
                    "Canonical expiry exceeds the exact persistent timestamp range"
                )
            rows.expiry[name] = deadline
        else:
            if existing_expiry is not None:
                raise ConfigurationError("Terminal evidence cannot revert to an unresolved stage")
            rows.expiry.pop(name, None)
    for index in names(delta["token_index_delete"], limit=258):
        if rows.indexes.get(index) in deletion:
            rows.indexes.pop(index, None)
    updates = strings(delta["token_index_put"], key_limit=258, value_limit=256)
    for index, owner in updates.items():
        if owner not in put and rows.indexes.get(index) != owner:
            raise ConfigurationError("A new canonical index requires its owner row update")
    rows.indexes.update(updates)
    return rows


class CanonicalComponents:
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
        owner = cast("MemoryIdleBackend", self)
        await owner.require_storage_format(3)
        async with owner._lock:
            revision, hot, _ = body(owner._records.get(key), component)
            rows = owner._canonical_rows.get((key, component), CanonicalRows())
            return observe(
                rows,
                revision,
                hot,
                now_ms=round(owner._now() * 1000),
                operation_id=operation_id,
                token=token,
                reservation_id=reservation_id,
                index_keys=index_keys,
            )

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
        owner = cast("MemoryIdleBackend", self)
        await owner.require_storage_format(3)
        async with owner._lock:
            revision, _, old_identity = body(owner._records.get(key), component)
            next_revision, hot, identity = body(record, component)
            assert identity is not None
            delta = delta_payload(
                ledger_delta, identity=identity, max_bytes=owner.config.max_components_bytes
            )
            if delta["expected_revision"] != revision:
                raise VersionConflict("Canonical ledger revision changed")
            if old_identity is not None and old_identity != identity:
                raise ConfigurationError("Canonical component identity changed")
            if next_revision != delta["revision"] or hot != delta["hot"]:
                raise ConfigurationError("Hot projection and canonical delta disagree")
            previous = owner._canonical_rows.get((key, component), CanonicalRows())
            updated = apply_rows(
                previous,
                delta,
                now_ms=round(owner._now() * 1000),
                limit=owner.config.max_receipts_per_conversation,
            )
            before = owner._records.get(key)
            before_policy = owner._policies.get(key)
            before_job = copy(owner._queue.jobs.get(key))
            try:
                with owner._receipts.transient():
                    if finalize_idle_operation_id is not None:
                        if (
                            before is None
                            or expected_version is None
                            or before.idle.operation is None
                            or before.idle.operation.operation_id != finalize_idle_operation_id
                        ):
                            raise OwnershipLost("Canonical completion lost its idle operation")
                        if coordination_scope is None or not owner.coordinator.scope_matches(
                            key, coordination_scope
                        ):
                            raise OwnershipLost(
                                "Canonical completion requires the current owned scope"
                            )
                        if record.session != before.session or record.idle.operation is not None:
                            raise ActivityConflict(
                                "Canonical completion cannot change or extend authentication"
                            )
                        old_owner, new_owner = ownership(before), ownership(record)
                        if (
                            old_owner is None
                            or new_owner is None
                            or old_owner["component"] != component
                            or new_owner["component"] != component
                        ):
                            raise ActivityConflict(
                                "Canonical completion changed component ownership"
                            )

                        def untouched(value: Mapping[str, object]) -> dict[str, object]:
                            return {
                                name: item
                                for name, item in value.items()
                                if name not in {component, "__idle_owner__"}
                            }

                        if untouched(record.components) != untouched(before.components):
                            raise ActivityConflict(
                                "Canonical completion changed unrelated component evidence"
                            )
                        if record.activity is not None and (
                            record.activity.session_id != before.session.session_id
                            or record.activity.expires_at > before.session.expires_at
                        ):
                            raise ActivityConflict(
                                "Canonical activity exceeds its authorized session"
                            )
                        check_manifest(
                            owner._manifest.generation if owner._manifest else None,
                            expected_manifest,
                        )
                        result = await owner.transition(
                            key,
                            expected_version=expected_version,
                            operation_id="canonical-complete:" + finalize_idle_operation_id,
                            fingerprint=fingerprint(delta, engine=owner.config.engine),
                            transform=lambda _: record,
                            claim=claim,
                            policy=policy,
                            coordination_scope=coordination_scope,
                        )
                    else:
                        result = await owner.component_transaction(
                            key,
                            component=component,
                            expected_version=expected_version,
                            operation_id="canonical:" + str(next_revision),
                            fingerprint=fingerprint(delta, engine=owner.config.engine),
                            record=record,
                            policy=policy,
                            coordination_scope=coordination_scope,
                            expected_manifest=expected_manifest,
                            allow_idle_operation_id=allow_idle_operation_id,
                            expires_at=expires_at,
                            claim=claim,
                        )
                owner._canonical_rows[(key, component)] = updated
            except BaseException:
                if before is None:
                    owner._records.pop(key, None)
                else:
                    owner._records[key] = before
                if before_policy is None:
                    owner._policies.pop(key, None)
                else:
                    owner._policies[key] = before_policy
                if before_job is None:
                    owner._queue.jobs.pop(key, None)
                else:
                    owner._queue.jobs[key] = before_job
                    owner._queue._push(key, before_job)
                raise
            return result
