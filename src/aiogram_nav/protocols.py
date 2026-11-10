"""Idle-independent extension contracts for navigation coordination and effects."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Hashable
from contextlib import AbstractAsyncContextManager
from typing import Protocol, TypeVar

T = TypeVar("T")


class Coordinator(Protocol):
    @property
    def active_scopes(self) -> int: ...
    def hold(self, key: Hashable) -> AbstractAsyncContextManager[None]: ...
    def scope_token(self, key: Hashable) -> object | None: ...
    def scope_active(self, token: object) -> bool: ...
    def scope_matches(self, key: Hashable, token: object) -> bool: ...


class EffectRecorder(Protocol):
    async def run(
        self, stage: str, callback: Callable[[], Awaitable[T]], *, replay_safe: bool = False
    ) -> T: ...
