"""A user activation owns one replay result, including its session projection."""

from dataclasses import replace

import pytest

from aiogram_idle import ActivityGuard
from aiogram_idle.errors import ActivityConflict, OperationIdConflict
from tests.test_external_sessions import FLOW, KEY, build


async def prepare():
    runtime, backend, authority, adapter, presenter, clock = await build()
    await backend.activate_storage_format(
        expected=2, target=3, operation_id="format3", old_workers_drained=True, dry_run=False
    )
    return runtime, backend, authority, adapter, presenter, clock


async def test_one_canonical_receipt_per_external_activation_and_exact_replay():
    runtime, backend, _, _, _, _ = await prepare()
    context = runtime.for_conversation(KEY)
    activity = None
    for index in range(200):
        accepted = await context.activate(
            FLOW, operation_id=str(index), expected=activity.guard if activity else None
        )
        assert (
            await context.activate(
                FLOW, operation_id=str(index), expected=activity.guard if activity else None
            )
            == accepted
        )
        activity = accepted
    assert len(backend._receipts.items[KEY]) == 200
    assert all(not key.startswith("idle:") for key in backend._receipts.items[KEY])
    assert (await context.activate(FLOW, operation_id="0")) == backend._receipts.items[KEY][
        "0"
    ].result


async def test_failed_entry_rolls_back_binding_and_generation_atomically():
    runtime, backend, _, _, _, _ = await prepare()
    context = runtime.for_conversation(KEY)
    with pytest.raises(ActivityConflict):
        await context.activate(FLOW, operation_id="failed", expected=ActivityGuard("bad", "bad", 1))
    assert await backend.load(KEY) is None
    assert backend._receipts.items.get(KEY, {}) == {}
    assert KEY not in backend._queue.jobs
    accepted = await context.activate(FLOW, operation_id="success")
    assert accepted.activity_revision == 1


async def test_replay_fingerprint_rejects_changed_flow_and_authority():
    runtime, backend, authority, _, _, _ = await prepare()
    context = runtime.for_conversation(KEY)
    await context.activate(FLOW, operation_id="same")
    with pytest.raises(OperationIdConflict):
        await context.activate(replace(FLOW, params={"draft_id": "other"}), operation_id="same")
    authority.value = replace(authority.value, session_id="different")
    with pytest.raises(OperationIdConflict):
        await context.activate(FLOW, operation_id="same")
    assert len(backend._receipts.items[KEY]) == 1


async def test_expired_replay_allows_more_than_ten_times_capacity_without_eviction():
    runtime, backend, _, _, _, clock = await prepare()
    # Backend owns the immutable configuration selected at construction. A small
    # receipt budget is exercised directly without mutating its public config.
    backend._receipts.limit = 3
    backend._receipts.retention = 2
    activity = None
    for index in range(40):
        activity = await runtime.for_conversation(KEY).activate(
            FLOW, operation_id=str(index), expected=activity.guard if activity else None
        )
        assert len(backend._receipts.items[KEY]) <= 3
        clock.advance(1)
