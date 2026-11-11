"""Injectable wall and monotonic clocks for live runtimes and deterministic tests."""

from __future__ import annotations

import asyncio
import math
import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...
    def monotonic(self) -> float: ...
    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class ManualClock:
    """Advance explicitly; sleeping tasks wake without real-time delays."""

    def __init__(self, now: float = 1_700_000_000.0) -> None:
        if not math.isfinite(now):
            raise ValueError("clock time must be finite")
        self._now = now
        self._monotonic = 0.0
        self._waiters: list[tuple[float, asyncio.Future[None]]] = []

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("clock advance must be finite and nonnegative")
        self._now += seconds
        self._monotonic += seconds
        remaining: list[tuple[float, asyncio.Future[None]]] = []
        for deadline, future in self._waiters:
            if deadline <= self._monotonic:
                if not future.done():
                    future.set_result(None)
            elif not future.done():
                remaining.append((deadline, future))
        self._waiters = remaining

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        future = asyncio.get_running_loop().create_future()
        item = (self._monotonic + seconds, future)
        self._waiters.append(item)
        try:
            await future
        finally:
            if item in self._waiters:
                self._waiters.remove(item)
