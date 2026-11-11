"""Check an independently installed distribution and optional-dependency boundary."""

from __future__ import annotations

import argparse
import asyncio
from importlib.metadata import version
from importlib.resources import files
from importlib.util import find_spec

from aiogram_coordination import CoordinationKey, MemoryCoordinator, __version__


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis", action="store_true")
    args = parser.parse_args()
    if __version__ != version("aiogram-coordination"):
        raise RuntimeError("Runtime/distribution version mismatch")
    if not files("aiogram_coordination").joinpath("py.typed").is_file():
        raise RuntimeError("Typed marker missing")
    for peer in ("aiogram_idle", "aiogram_nav", "aiogram_kit"):
        if find_spec(peer) is not None:
            raise RuntimeError("Standalone probe must not include peer libraries")
    if (find_spec("redis") is not None) != args.redis:
        raise RuntimeError("Optional Redis presence differs from requested profile")

    async def probe() -> None:
        coordinator = MemoryCoordinator()
        key = CoordinationKey("installation", 1, 2, 2)
        async with coordinator.hold(key):
            if not coordinator.owns(key):
                raise RuntimeError("Memory ownership probe failed")

    asyncio.run(probe())
    print("Installed coordination: version, typing, scope and standalone dependencies verified")


if __name__ == "__main__":
    main()
