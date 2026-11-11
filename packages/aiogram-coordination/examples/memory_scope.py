"""Run a standalone memory scope without any Redis or peer package."""

import asyncio
import logging

from aiogram_coordination import CoordinationKey, MemoryCoordinator


async def main() -> None:
    coordinator = MemoryCoordinator()
    key = CoordinationKey("example", 1, 42, 42)
    async with coordinator.hold(key):
        logging.getLogger("aiogram_coordination.example").debug("Protected scope entered")
        if not coordinator.owns(key):
            raise RuntimeError("Ownership was not acquired")
    print("Scope completed; no network calls were made.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("aiogram_coordination").setLevel(logging.DEBUG)
    asyncio.run(main())
