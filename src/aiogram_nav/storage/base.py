"""Idle-independent persistence protocol implemented by navigation repositories."""

from __future__ import annotations

from typing import Protocol

from ..clock import Clock
from ..config import NavigationConfig
from ..models import (
    ActionStatus,
    CommitResult,
    ConversationKey,
    EffectCheckpoint,
    NavigationIntent,
    NavigationMutation,
    NavigationToken,
    PreparedAction,
    VersionedSnapshot,
)
from ..protocols import Coordinator


class NavigationRepository(Protocol):
    clock: Clock
    config: NavigationConfig
    coordinator: Coordinator
    capabilities: frozenset[str]

    def bind_coordinator(self, coordinator: Coordinator) -> None: ...

    async def load(self, key: ConversationKey) -> VersionedSnapshot | None: ...
    async def prepare(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        intent: NavigationIntent,
        coordination_scope: object | None = None,
    ) -> PreparedAction: ...
    async def checkpoint(
        self,
        key: ConversationKey,
        *,
        operation_id: str,
        effect: EffectCheckpoint,
        coordination_scope: object | None = None,
    ) -> PreparedAction: ...
    async def lookup_operation(
        self, key: ConversationKey, *, operation_id: str
    ) -> ActionStatus: ...
    async def commit(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        mutation: NavigationMutation,
        coordination_scope: object | None = None,
    ) -> CommitResult: ...
    async def pending(self, key: ConversationKey) -> PreparedAction | None: ...
    async def mark_unknown(self, key: ConversationKey, *, operation_id: str) -> None: ...
    async def abandon(
        self, key: ConversationKey, operation_id: str, *, expected_session_id: str
    ) -> None: ...
    async def reserve_token(
        self, key: ConversationKey, token: NavigationToken, *, operation_id: str
    ) -> NavigationToken: ...
    async def resolve_token(self, key: ConversationKey, token: str) -> NavigationToken | None: ...
    async def consume_token(
        self, key: ConversationKey, token: str, *, actor_id: int, operation_id: str
    ) -> NavigationToken: ...
    async def sweep(self, *, limit: int = 100) -> int: ...
    async def close(self) -> None: ...
