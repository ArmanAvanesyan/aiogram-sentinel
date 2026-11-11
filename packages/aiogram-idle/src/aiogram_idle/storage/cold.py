"""Bounded format-three state reads and immutable, independently expiring results."""

from __future__ import annotations

# A Redis Engine is an ephemeral backend-owned domain reducer, not a cache.
# pyright: reportPrivateUsage=false
import hashlib
import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from ..errors import BackendInconsistent, ConfigurationMismatch
from ..models import IdleConversationKey, PendingOperation, RuntimeSnapshot
from .codec import decode, encode
from .cold_scripts import READ_COLD
from .redis_engine import Engine
from .redis_transport import array, text
from .state import OperationReceipt
from .wire_json import compact, strict

if TYPE_CHECKING:
    from .redis_store import RedisStore


def receipt_key(store: RedisStore, key: IdleConversationKey, operation_id: str) -> str:
    return (
        f"{store.prefix}:receipt:{store.ident(key)}:"
        + hashlib.sha256(operation_id.encode("utf-8", "surrogatepass")).hexdigest()
    )


MAX_EXACT_MILLISECONDS = 2**53 - 1


def replay_milliseconds(seconds: float, *, now: float = 0) -> int:
    """Validate an exact Redis integer deadline before constructing a write delta."""
    duration = seconds * 1000
    if not math.isfinite(duration) or duration <= 0:
        raise ConfigurationMismatch("Replay retention must fit an exact Redis millisecond TTL")
    milliseconds = math.ceil(duration)
    if milliseconds > MAX_EXACT_MILLISECONDS - math.floor(now * 1000):
        raise ConfigurationMismatch(
            "Replay retention exceeds Redis exact millisecond deadline range"
        )
    return milliseconds


def receipt_prefix(store: RedisStore, key: IdleConversationKey) -> str:
    return f"{store.prefix}:receipt:{store.ident(key)}:"


def result_prefix(store: RedisStore, key: IdleConversationKey) -> str:
    return f"{store.prefix}:result:{store.ident(key)}:"


def keys(store: RedisStore, key: IdleConversationKey, operation_id: str = "") -> list[str]:
    ident = store.ident(key)
    return [
        f"{store.prefix}:pending:{ident}",
        f"{store.prefix}:receipt-index:{ident}",
        f"{store.prefix}:receipt-expiry:{ident}",
        receipt_key(store, key, operation_id),
    ]


@dataclass
class ColdState:
    operation_id: str
    count: int
    expired: tuple[str, ...]
    legacy: bool = False


def hot_payload(engine: Engine) -> tuple[str, str]:
    record = engine._records.get(engine.key)
    if record is None:
        return "", ""
    operation = record.idle.operation
    state = {
        "record": replace(record, idle=replace(record.idle, operation=None)),
        "armed_epoch": engine.armed_epoch,
        "policy": engine._policies.get(engine.key),
        "tokens": engine._tokens.get(engine.key, {}),
        "receipts": {},
        "pruned_before": engine._receipts.pruned_before,
    }
    hot = compact(
        {
            "schema_version": 3,
            "kind": "idle-hot",
            "pending_ref": operation.operation_id if operation else None,
            "state": encode(state, schema_version=3),
        }
    )
    pending = (
        compact(
            {
                "key": encode(engine.key),
                "operation_id": operation.operation_id,
                "value": encode(operation, schema_version=3),
            }
        )
        if operation
        else ""
    )
    return hot, pending


def state_payload(hot: str, pending: str, key: IdleConversationKey) -> dict[str, object]:
    body = strict(hot)
    if (
        set(body) != {"schema_version", "kind", "pending_ref", "state"}
        or body["schema_version"] != 3
        or body["kind"] != "idle-hot"
        or not isinstance(body["state"], str)
    ):
        raise BackendInconsistent("Invalid format-three hot state")
    decoded = decode(body["state"])
    if not isinstance(decoded, dict):
        raise BackendInconsistent("Invalid hot domain state")
    state = cast(dict[str, object], decoded)
    record = state.get("record")
    if (
        not isinstance(record, RuntimeSnapshot)
        or record.key != key
        or record.idle.operation is not None
        or state.get("receipts") != {}
    ):
        raise BackendInconsistent("Hot state contains duplicated recovery evidence")
    reference = body["pending_ref"]
    if reference is None:
        if pending:
            raise BackendInconsistent("Unreferenced protected operation evidence")
    else:
        if not isinstance(reference, str) or not pending:
            raise BackendInconsistent("Protected operation evidence is missing")
        row = strict(pending)
        if (
            set(row) != {"key", "operation_id", "value"}
            or row["key"] != encode(key)
            or row["operation_id"] != reference
            or not isinstance(row["value"], str)
        ):
            raise BackendInconsistent("Protected operation identity changed")
        operation = decode(row["value"])
        if not isinstance(operation, PendingOperation) or operation.operation_id != reference:
            raise BackendInconsistent("Protected operation reference changed")
        state["record"] = replace(record, idle=replace(record.idle, operation=operation))
    return state


async def read(
    store: RedisStore,
    key: IdleConversationKey,
    *,
    operation_id: str = "",
    allow_parked: bool = False,
) -> tuple[Engine, str, str]:
    base, cold = store.keys(key), keys(store, key, operation_id)
    values = array(
        await store.connection.script(
            READ_COLD,
            [
                base[0],
                base[1],
                base[3],
                base[4],
                store.prefix + ":created",
                store.prefix + ":config-established",
                store.prefix + ":parked",
                *cold,
            ],
            [store.member(key), store.history, operation_id, result_prefix(store, key)],
            mutation=False,
        )
    )
    if len(values) != 13:
        raise BackendInconsistent("Invalid format-three observation response")
    raw, job, config = (text(item) for item in values[:3])
    now = int(text(values[4])) + int(text(values[5])) / 1_000_000
    store.clock.update(now)
    if not allow_parked and values[6]:
        raise BackendInconsistent(
            "Redis conversation is parked; explicit administrative release required"
        )
    if not raw and (job or values[3]):
        raise BackendInconsistent("Retained Redis runtime is missing")
    pending, receipt, blob, expiry = (text(item) for item in values[7:11])
    if not raw and pending:
        raise BackendInconsistent("Protected pending evidence has no hot owner")
    count = int(cast(int, values[11]))
    expired = tuple(text(item) for item in array(values[12]))
    legacy = bool(raw and strict(raw).get("kind") != "idle-hot")
    prepared = raw
    loaded: dict[str, OperationReceipt[object]] = {}
    if not legacy:
        state = state_payload(raw, pending, key) if raw else None
        if receipt and expiry and float(expiry) > now * 1000:
            row = strict(receipt)
            if (
                set(row)
                != {
                    "schema_version",
                    "key",
                    "operation_id",
                    "fingerprint",
                    "expires_at",
                    "result",
                    "result_ref",
                }
                or row["schema_version"] != 3
                or row["key"] != store.member(key)
                or row["operation_id"] != operation_id
                or not isinstance(row["fingerprint"], str)
                or not 1 <= len(row["fingerprint"]) <= 256
                or type(row["expires_at"]) is not int
                or row["expires_at"] != int(float(expiry))
            ):
                raise BackendInconsistent("Completed receipt identity changed")
            ref, inline = row["result_ref"], row["result"]
            if ref is not None:
                if (
                    not isinstance(ref, str)
                    or inline is not None
                    or not blob
                    or hashlib.sha256(blob.encode()).hexdigest() != ref
                ):
                    raise BackendInconsistent("Immutable result reference is missing or corrupt")
                result = decode(blob)
            else:
                if not isinstance(inline, str) or blob:
                    raise BackendInconsistent("Malformed inline replay result")
                result = decode(inline)
            loaded[operation_id] = OperationReceipt(
                row["fingerprint"], result, int(float(expiry)) / 1000
            )
        if state is not None:
            state["receipts"] = loaded
            prepared = encode(state, schema_version=3)
        elif loaded:
            # Expired/pruned conversations may still have promised replay evidence.
            # The Engine accepts this separately without inventing a live session.
            prepared = ""
    engine = Engine(
        key=key,
        raw=prepared,
        job=job,
        manifest=store.config_value(config),
        now=now,
        config=store.config,
        created_at=store.created_at,
        disarm_epoch=cast(str, store.config_envelope(config)["disarm_epoch"]) if config else "",
        storage_format=3,
    )
    engine.original_job = job
    engine.cold_state = ColdState(operation_id, count, expired, legacy)
    if not legacy:
        engine._receipts.items[key] = loaded
        engine._receipts.unloaded_count = max(0, count - len(loaded) - len(expired))
    return engine, raw, config


def commit_payload(store: RedisStore, engine: Engine) -> tuple[list[str], str]:
    context = cast(ColdState, engine.cold_state)
    if context.legacy:
        raise ConfigurationMismatch(
            "Migrate the retained legacy record before format-three mutation"
        )
    key, operation_id = engine.key, context.operation_id
    pending_key, metadata, expiry, row_key = keys(store, key, operation_id)
    _, pending = hot_payload(engine)
    receipt = engine._receipts.items.get(key, {}).get(operation_id)
    blob, row, blob_key = "", "", result_prefix(store, key) + "unused"
    if receipt is not None:
        encoded = encode(receipt.result, schema_version=3)
        ref = None
        if isinstance(receipt.result, RuntimeSnapshot):
            blob, ref = encoded, hashlib.sha256(encoded.encode()).hexdigest()
            blob_key = result_prefix(store, key) + ref
        row = compact(
            {
                "schema_version": 3,
                "key": store.member(key),
                "operation_id": operation_id,
                "fingerprint": receipt.fingerprint,
                "expires_at": 0,
                "result": None if ref else encoded,
                "result_ref": ref,
            }
        )
    garbage = [{"id": item, "key": receipt_key(store, key, item)} for item in context.expired]
    payload = compact(
        {
            "pending": pending,
            "operation_id": operation_id,
            "row": row,
            "blob": blob,
            "retention_ms": replay_milliseconds(
                store.config.effective_replay_retention_seconds, now=store.clock.now()
            ),
            "receipt_prefix": receipt_prefix(store, key),
            "result_prefix": result_prefix(store, key),
            "gc": garbage,
        }
    )
    return [
        pending_key,
        metadata,
        expiry,
        row_key,
        blob_key,
        store.prefix + ":receipt-sweep",
        *(item["key"] for item in garbage),
    ], payload
