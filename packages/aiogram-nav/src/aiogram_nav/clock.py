"""Injectable epoch-millisecond and monotonic clocks."""

from __future__ import annotations

import asyncio
import math
import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> int: ...
    def now_ms(self) -> int: ...
    def monotonic(self) -> float: ...
    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> int:
        return time.time_ns() // 1_000_000

    def now_ms(self) -> int:
        return self.now()

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class ManualClock:
    def __init__(self, initial_ms: int = 0) -> None:
        if type(initial_ms) is not int:
            raise ValueError("Initial time must be integer milliseconds")
        self._now = initial_ms
        self._mono = 0.0

    def now(self) -> int:
        return self._now

    def now_ms(self) -> int:
        return self.now()

    def monotonic(self) -> float:
        return self._mono

    def advance(self, milliseconds: int) -> None:
        if type(milliseconds) is not int or milliseconds < 0:
            raise ValueError("Advance must be nonnegative integer milliseconds")
        self._now += milliseconds
        self._mono += milliseconds / 1000

    async def sleep(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Sleep duration must be finite and nonnegative")
        self.advance(int(seconds * 1000))
        await asyncio.sleep(0)
