"""Idle-independent extension contracts for navigation coordination and effects."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from aiogram_coordination import Coordinator as Coordinator

T = TypeVar("T")


class EffectRecorder(Protocol):
    async def run(
        self, stage: str, callback: Callable[[], Awaitable[T]], *, replay_safe: bool = False
    ) -> T: ...
