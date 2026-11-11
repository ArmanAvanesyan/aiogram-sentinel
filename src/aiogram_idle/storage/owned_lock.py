"""Backend-only task-owned lock for composing pure domain mutations atomically."""

from __future__ import annotations

import asyncio
from typing import Literal


class OwnedLock(asyncio.Lock):
    """Reenter only from the actual owning task, never an inherited context."""

    def __init__(self) -> None:
        super().__init__()
        self._owner: asyncio.Task[object] | None = None
        self._depth = 0

    async def acquire(self) -> Literal[True]:
        task = asyncio.current_task()
        if task is not None and self._owner is task:
            self._depth += 1
            return True
        await super().acquire()
        self._owner, self._depth = task, 1
        return True

    def release(self) -> None:
        if self._owner is not asyncio.current_task() or self._depth < 1:
            raise RuntimeError("Backend lock release requires its owning task")
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            super().release()
