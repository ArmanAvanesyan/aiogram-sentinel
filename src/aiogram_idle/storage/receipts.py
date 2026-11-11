"""Bounded, fingerprinted operation receipts for memory storage."""

from __future__ import annotations

import json
from collections.abc import Generator, Hashable, Mapping
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, TypeVar, cast

from ..errors import OperationIdConflict, Overloaded
from ..models import timestamp, validate_identifier
from .state import OperationLookup, OperationReceipt

T = TypeVar("T")


def _canonical(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item) for key, item in cast(Mapping[object, object], value).items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in cast(tuple[object, ...], value)]
    return value


def fingerprint(value: object, *, engine: Literal["python", "rust"] = "python") -> str:
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    from ..engines import fingerprint_canonical

    return fingerprint_canonical(encoded, engine=engine)


class Receipts:
    def __init__(
        self, *, limit: int, retention: float, engine: Literal["python", "rust"] = "python"
    ) -> None:
        self.engine: Literal["python", "rust"] = engine
        self.unloaded_count = 0
        self.limit = limit
        self.retention = retention
        self.items: dict[Hashable, dict[str, OperationReceipt[object]]] = {}
        self.pruned_before = float("-inf")
        self._transient = 0

    @contextmanager
    def transient(self) -> Generator[None, None, None]:
        """Compose internal pure stages without claiming independent replay slots.

        The backend owner must hold its task-owned lock and save one canonical
        user receipt after all stages succeed. This is never a public bypass.
        """
        self._transient += 1
        try:
            yield
        finally:
            self._transient -= 1

    def lookup(self, key: Hashable, operation_id: str, digest: str) -> object | None:
        receipt = self.items.get(key, {}).get(operation_id)
        if receipt is not None and receipt.fingerprint != digest:
            raise OperationIdConflict("The operation ID was reused for different input")
        return receipt.result if receipt else None

    def prepare(
        self, key: Hashable, operation_id: str, digest: str, *, now: float
    ) -> object | None:
        validate_identifier(operation_id, "operation_id")
        if self._transient:
            return None
        self.pruned_before = max(self.pruned_before, now - self.retention)
        receipts = self.items.get(key, {})
        for previous, receipt in tuple(receipts.items()):
            if receipt.expires_at <= now:
                del receipts[previous]
        from ..engines import receipt_admission

        prior = receipts.get(operation_id)
        verdict = receipt_admission(
            prior.fingerprint if prior else None,
            digest,
            len(receipts) + self.unloaded_count,
            self.limit,
            engine=self.engine,
        )
        duplicate = self.lookup(key, operation_id, digest)
        if verdict == "capacity":
            raise Overloaded(
                "Operation receipt capacity is exhausted",
                reason="replay_slots",
                limit=self.limit,
                used=len(receipts) + self.unloaded_count,
                earliest_safe_expiry=min(
                    (receipt.expires_at for receipt in receipts.values()), default=None
                )
                if not self.unloaded_count
                else None,
            )
        return duplicate

    def save(self, key: Hashable, operation_id: str, digest: str, result: T, *, now: float) -> T:
        if self._transient:
            return result
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
