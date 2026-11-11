"""Expired positive evidence must never turn into proof of absence."""

from aiogram_idle.storage.receipts import Receipts, lookup_operation
from aiogram_idle.storage.state import OperationReceipt


def test_expired_receipt_is_unknown_even_inside_callers_longer_retention():
    receipts = Receipts(limit=10, retention=100)
    receipts.items["conversation"] = {"op": OperationReceipt("input", True, expires_at=1001)}
    result = lookup_operation(
        receipts, "conversation", "op", now=1002, created_at=1000, not_before=1000
    )
    assert result.status == "unknown_history"
