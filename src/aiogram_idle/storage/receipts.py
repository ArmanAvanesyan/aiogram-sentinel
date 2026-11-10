"""Bounded, fingerprinted operation receipts for memory storage."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Hashable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import TypeVar, cast

from ..errors import OperationIdConflict, Overloaded
from ..models import timestamp
from .state import OperationLookup, OperationReceipt

T = TypeVar("T")


def _canonical(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item) for key, item in cast(Mapping[object, object], value).items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in cast(tuple[object, ...], value)]
    return value


def fingerprint(value: object) -> str:
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


class Receipts:
    def __init__(self, *, limit: int, retention: float) -> None:
        self.limit = limit
        self.retention = retention
        self.items: dict[Hashable, dict[str, OperationReceipt[object]]] = {}
        self.pruned_before = float("-inf")

    def lookup(self, key: Hashable, operation_id: str, digest: str) -> object | None:
        receipt = self.items.get(key, {}).get(operation_id)
        if receipt is not None and receipt.fingerprint != digest:
            raise OperationIdConflict("The operation ID was reused for different input")
        return receipt.result if receipt else None

    def prepare(
        self, key: Hashable, operation_id: str, digest: str, *, now: float
    ) -> object | None:
        if not operation_id or len(operation_id) > 256:
            raise ValueError("operation_id must contain 1 to 256 characters")
        self.pruned_before = max(self.pruned_before, now - self.retention)
        receipts = self.items.get(key, {})
        for previous, receipt in tuple(receipts.items()):
            if receipt.expires_at <= now:
                del receipts[previous]
        duplicate = self.lookup(key, operation_id, digest)
        if duplicate is None and len(receipts) >= self.limit:
            raise Overloaded(
                "Operation receipt capacity is exhausted",
                reason="replay_slots",
                limit=self.limit,
                used=len(receipts),
                earliest_safe_expiry=min(receipt.expires_at for receipt in receipts.values()),
            )
        return duplicate

    def save(self, key: Hashable, operation_id: str, digest: str, result: T, *, now: float) -> T:
        self.items.setdefault(key, {})[operation_id] = OperationReceipt(
            digest, cast(object, result), now + self.retention
        )
        return result


def lookup_operation(
    receipts: Receipts,
    key: Hashable,
    operation_id: str,
    *,
    now: float,
    created_at: float,
    not_before: float | None,
) -> OperationLookup:
    receipt = receipts.items.get(key, {}).get(operation_id)
    if receipt is not None:
        if receipt.expires_at > now:
            return OperationLookup("found", receipt.result)
        # Expired evidence proves that history existed; it cannot prove absence.
        return OperationLookup("unknown_history")
    if not_before is not None:
        since = timestamp(not_before)
        # Retention expiry is exclusive: a receipt written exactly at the
        # retention boundary can already have been pruned.
        if created_at <= since <= now and since > max(
            receipts.pruned_before, now - receipts.retention
        ):
            return OperationLookup("not_found_within_retention")
    return OperationLookup("unknown_history")
