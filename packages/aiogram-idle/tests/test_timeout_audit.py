"""Timeout scopes consume their own cancellation and preserve external requests."""

import asyncio

import pytest

from aiogram_idle.compat import bounded


def cancelling(task):
    return getattr(task, "cancelling", lambda: 0)()


async def test_timeout_releases_its_cancellation_count():
    task = asyncio.current_task()
    before = cancelling(task)
    with pytest.raises(asyncio.TimeoutError):
        async with bounded(0):
            await asyncio.Event().wait()
    assert cancelling(task) == before


async def test_suppressed_timeout_also_releases_its_request():
    task = asyncio.current_task()
    before = cancelling(task)
    async with bounded(0):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
    assert cancelling(task) == before


async def test_external_cancellation_is_not_a_timeout():
    entered = asyncio.Event()

    async def body():
        async with bounded(30):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(body())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize("external_message", [None, "external"])
async def test_racing_external_cancel_preserved(external_message):
    observed = []

    async def body():
        task = asyncio.current_task()
        async with bounded(0):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                task.cancel(external_message)
                raise

    task = asyncio.create_task(body())
    try:
        await task
    except asyncio.CancelledError:
        observed.append("cancelled")
    except asyncio.TimeoutError:
        observed.append("timeout")
    assert observed == ["cancelled"]
    assert cancelling(task) in {0, 1}  # Python 3.10 has no public counter.


async def test_nested_timeouts_do_not_leave_a_stale_count():
    task = asyncio.current_task()
    before = cancelling(task)
    with pytest.raises(asyncio.TimeoutError):
        async with bounded(0):
            async with bounded(30):
                await asyncio.Event().wait()
    assert cancelling(task) == before


async def test_delegated_capability_is_bound_to_its_conversation():
    from aiogram_idle.coordinator import MemoryCoordinator

    coordinator = MemoryCoordinator()
    async with coordinator.hold("first"):
        scope = coordinator.scope_token("first")
        assert coordinator.scope_matches("first", scope)
        assert not coordinator.scope_matches("second", scope)

        async def child():
            assert not coordinator.owns("first")
            assert coordinator.scope_matches("first", scope)
            assert not coordinator.scope_matches("second", scope)

        await asyncio.create_task(child())
    assert not coordinator.scope_matches("first", scope)


async def test_worker_loop_survives_child_cancellation_after_an_owned_timeout(monkeypatch):
    from unittest.mock import AsyncMock

    from tests.runtime_helpers import make_harness

    harness = await make_harness()
    calls = []

    async def poll():
        calls.append("poll")
        if len(calls) == 1:
            with pytest.raises(asyncio.TimeoutError):
                async with bounded(0):
                    await asyncio.Event().wait()
        elif len(calls) == 2:
            raise asyncio.CancelledError  # Child operation, not external loop stop.
        else:
            harness.runtime._stopping = True

    async def sleep(seconds):
        await asyncio.sleep(0)

    monkeypatch.setattr(harness.runtime, "run_once", poll)
    monkeypatch.setattr(harness.runtime, "reconcile", AsyncMock())
    monkeypatch.setattr(harness.clock, "sleep", sleep)
    await asyncio.wait_for(harness.runtime._loop(), timeout=2)
    assert calls == ["poll", "poll", "poll"]


async def test_nested_simultaneous_owned_timeouts_stay_timeout_errors():
    task = asyncio.current_task()
    before = cancelling(task)
    with pytest.raises(asyncio.TimeoutError):
        async with bounded(0):
            async with bounded(0):
                await asyncio.Event().wait()
    assert cancelling(task) == before
