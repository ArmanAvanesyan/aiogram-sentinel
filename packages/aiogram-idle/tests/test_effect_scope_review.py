"""Separate effect recorders in a delegated scope share stage reservations."""

import asyncio

from aiogram_idle.effects import OperationEffects
from tests.runtime_helpers import make_harness


async def test_two_recorders_do_not_repeat_replay_safe_external_effect():
    harness = await make_harness()
    calls = []
    original = harness.presenter.show

    async def show(request):
        record = await harness.backend.load(harness.key)
        operation = record.idle.operation
        first = OperationEffects(harness.runtime, harness.key, operation.operation_id, None)
        second = OperationEffects(harness.runtime, harness.key, operation.operation_id, None)

        async def effect():
            calls.append("external")
            await asyncio.sleep(0)
            return "receipt"

        assert await asyncio.gather(
            first.run("delegated", effect, replay_safe=True),
            second.run("delegated", effect, replay_safe=True),
        ) == ["receipt", "receipt"]
        return await original(request)

    harness.presenter.show = show
    await harness.due()
    assert calls == ["external"]
