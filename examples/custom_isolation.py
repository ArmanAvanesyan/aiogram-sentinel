"""Runnable, network-free application-owned isolation with explicit lease proof."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiogram.fsm.storage.base import BaseEventIsolation, StorageKey
from aiogram.fsm.storage.memory import SimpleEventIsolation

from aiogram_coordination import (
    AiogramMemoryCoordinator,
    CoordinationKey,
    LeaseHandle,
    OwnershipLost,
    TrackedEventIsolation,
)


class ApplicationIsolation(BaseEventIsolation):
    def __init__(self) -> None:
        self.delegate = SimpleEventIsolation()

    @asynccontextmanager
    async def lock(self, key: StorageKey) -> AsyncGenerator[None, None]:
        async with self.delegate.lock(key=key):
            yield

    async def close(self) -> None:
        await self.delegate.close()


@dataclass
class Receipt:
    key: StorageKey
    lost: asyncio.Event

    @property
    def valid(self) -> bool:
        return not self.lost.is_set()

    def assert_owned(self) -> None:
        if not self.valid:
            raise OwnershipLost("Application lock ended")

    async def wait_lost(self) -> None:
        await self.lost.wait()


class ApplicationProvider:
    def __init__(self, isolation: ApplicationIsolation) -> None:
        self.isolation = isolation

    @asynccontextmanager
    async def acquire(self, key: StorageKey) -> AsyncGenerator[LeaseHandle, None]:
        async with self.isolation.lock(key=key):
            receipt = Receipt(key, asyncio.Event())
            try:
                yield receipt
            finally:
                receipt.lost.set()


async def main() -> None:
    application = ApplicationIsolation()
    isolation = TrackedEventIsolation(application, provider=ApplicationProvider(application))
    coordinator = AiogramMemoryCoordinator(isolation)
    conversation = CoordinationKey("example", 1, 42, 42)
    results: list[int] = []

    async def application_operation(number: int) -> None:
        async with coordinator.hold(conversation):
            results.append(number)
            await asyncio.sleep(0)

    await asyncio.gather(application_operation(1), application_operation(2))
    await isolation.close()
    await application.close()
    print("Serialized application operations:", results)


if __name__ == "__main__":
    asyncio.run(main())
