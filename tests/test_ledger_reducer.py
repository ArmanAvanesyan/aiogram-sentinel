"""Canonical projection retains only requested receipts and original activity evidence."""

import pytest

from aiogram_nav import ManualClock, NavigationConfig, SchemaUnsupported
from aiogram_nav.storage.ledger import LedgerRead
from aiogram_nav.storage.ledger_reducer import NavigationLedgerReducer
from tests.test_storage import KEY, enter


async def test_canonical_projection_round_trip_and_first_integration_result():
    clock = ManualClock(1000)
    config = NavigationConfig()
    first = NavigationLedgerReducer(
        KEY, LedgerRead(None, None, {}, 0, {}), clock=clock, config=config
    )
    _, result = await enter(first.repository)
    first.set_integration_payload("enter", {"activity_id": "first", "revision": 1})
    delta = first.delta()
    assert delta.expected_revision is None
    assert delta.terminal_retention_ms == {"enter": 3_600_000}
    read = LedgerRead(delta.revision, delta.hot, delta.put, 1, {"enter": 3_601_000})
    resumed = NavigationLedgerReducer(KEY, read, clock=clock, config=config)
    status = await resumed.repository.lookup_operation(KEY, operation_id="enter")
    assert status.result == result
    assert resumed.delta().terminal_retention_ms == {}
    with pytest.raises(SchemaUnsupported, match="immutable"):
        resumed.set_integration_payload("enter", {"activity_id": "later"})


async def test_unloaded_receipts_count_toward_capacity_without_snapshot_copies():
    from aiogram_nav import NavigationIntent, Overloaded

    clock = ManualClock(1000)
    config = NavigationConfig(max_receipts=2)
    reducer = NavigationLedgerReducer(
        KEY, LedgerRead(None, None, {}, 0, {}), clock=clock, config=config
    )
    await enter(reducer.repository)
    delta = reducer.delta()
    # The host intentionally omits unrelated retained rows from this bounded read.
    read = LedgerRead(delta.revision, delta.hot, {}, 2, {})
    bounded = NavigationLedgerReducer(KEY, read, clock=clock, config=config)
    current = await bounded.repository.load(KEY)
    with pytest.raises(Overloaded):
        await bounded.repository.prepare(
            KEY, expected_version=current.version, intent=NavigationIntent("new", "root")
        )
