"""Standalone managed shutdown must drain work before aiogram closes FSM resources."""

import asyncio

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram_coordination import TrackedEventIsolation

from aiogram_idle import IdleConfig, IdlePolicies, IdleRuntime, MemoryIdleBackend, PromptPolicy
from aiogram_idle.clock import ManualClock
from tests.runtime_helpers import Adapter, Presenter
from tests.test_external_sessions import KEY


async def test_managed_shutdown_drains_worker_before_fsm_isolation_close():
    order = []

    class Storage(MemoryStorage):
        async def close(self):
            order.append("storage")
            await super().close()

    class Isolation(TrackedEventIsolation):
        async def close(self):
            await super().close()
            order.append("isolation")

    clock = ManualClock(1000)
    runtime = IdleRuntime(
        backend=MemoryIdleBackend(clock=clock, config=IdleConfig(shutdown_seconds=1)),
        policies=IdlePolicies({"prompt": PromptPolicy()}),
        adapters={"form": Adapter()},
        presenter=Presenter(clock),
        namespace="test",
    )
    dispatcher = Dispatcher(storage=Storage(), events_isolation=Isolation(SimpleEventIsolation()))
    runtime.install(dispatcher)
    entered = asyncio.Event()

    async def work():
        async with runtime.coordinator.hold(KEY):
            entered.set()
            await runtime._wake.wait()
        order.append("worker")

    runtime._task = asyncio.create_task(work())
    await entered.wait()
    await dispatcher.emit_shutdown()
    assert order == ["worker", "storage", "isolation"]
    assert runtime._task is None
