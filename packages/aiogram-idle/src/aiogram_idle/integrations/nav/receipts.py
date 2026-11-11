"""Bounded mapped activity receipts retained with navigation operation receipts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from aiogram_nav.storage.state import Conversation

from ...errors import SchemaUnsupported
from ...models import ActivitySnapshot, JsonObject, freeze_object
from ...storage.codec import decode, encode


def preserve(
    value: JsonObject,
    previous: object,
    ledger: Conversation,
    *,
    operation_id: str | None = None,
    activity: ActivitySnapshot | None = None,
) -> JsonObject:
    receipts: dict[str, str] = {}
    if isinstance(previous, Mapping):
        old = cast(Mapping[str, object], previous).get("activity_receipts")
        if old is not None:
            if not isinstance(old, Mapping):
                raise SchemaUnsupported("Malformed mapped activity receipts")
            for key, receipt in cast(Mapping[object, object], old).items():
                if not isinstance(key, str) or not isinstance(receipt, str):
                    raise SchemaUnsupported("Malformed mapped activity receipt")
                if key in ledger.operations:
                    receipts[key] = receipt
    if operation_id is not None and activity is not None:
        receipts[operation_id] = encode(activity)
    return freeze_object({**value, "activity_receipts": receipts}, max_bytes=8_388_608)


def resolve(value: JsonObject, operation_id: str) -> ActivitySnapshot:
    receipts = value.get("activity_receipts")
    if not isinstance(receipts, Mapping) or operation_id not in receipts:
        raise SchemaUnsupported("Mapped activity receipt is not retained")
    raw = receipts[operation_id]
    if not isinstance(raw, str):
        raise SchemaUnsupported("Malformed mapped activity receipt")
    result = decode(raw)
    if not isinstance(result, ActivitySnapshot):
        raise SchemaUnsupported("Mapped receipt does not contain an activity snapshot")
    return result
