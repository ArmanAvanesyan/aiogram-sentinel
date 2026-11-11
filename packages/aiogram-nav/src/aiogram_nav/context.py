"""Conversation-scoped navigation, independent of FSM and idle storage."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import TYPE_CHECKING

from .errors import ConfigurationError
from .models import (
    ActionKind,
    ConversationKey,
    HistoryMode,
    NavigationSnapshot,
    PreparedAction,
    RenderResult,
)

if TYPE_CHECKING:
    from .navigation import Navigation


class NavigationContext:
    def __init__(
        self, navigation: Navigation, key: ConversationKey, operation_prefix: str | None = None
    ) -> None:
        self.navigation, self.key = navigation, key
        self.operation_prefix = operation_prefix
        self._sequence = 0
        self.control_handled = False

    def operation_id(self, supplied: str | None) -> str:
        if supplied is not None:
            return supplied
        if self.operation_prefix is None:
            raise ConfigurationError("Direct navigation calls require an operation_id")
        self._sequence += 1
        return sha256(f"{self.operation_prefix}:{self._sequence}".encode()).hexdigest()

    async def current(self) -> NavigationSnapshot | None:
        async with self.navigation.coordinator.hold(self.key):
            loaded = await self.navigation.repository.load(self.key)
            if loaded is None:
                return None
            from .errors import SessionExpired

            try:
                await self.navigation.authorize_session(self.key, loaded.snapshot.session_id)
            except SessionExpired:
                return None
            return loaded.snapshot

    async def go(
        self,
        node_id: str,
        *,
        params: Mapping[str, object] | None = None,
        history: HistoryMode = "push",
        source: str = "application",
        operation_id: str | None = None,
        accepted_activity: bool = True,
    ) -> RenderResult:
        return await self.navigation.perform(
            self.key,
            "go",
            node_id=node_id,
            params=params,
            history=history,
            source=source,
            operation_id=self.operation_id(operation_id),
            accepted_activity=accepted_activity,
        )

    async def back(
        self, *, source: str = "application", operation_id: str | None = None
    ) -> RenderResult:
        return await self.navigation.perform(
            self.key, "back", source=source, operation_id=self.operation_id(operation_id)
        )

    async def home(
        self,
        *,
        root: str | None = None,
        source: str = "application",
        operation_id: str | None = None,
    ) -> RenderResult:
        return await self.navigation.perform(
            self.key,
            "home",
            node_id=root,
            source=source,
            operation_id=self.operation_id(operation_id),
        )

    async def cancel(
        self, *, source: str = "application", operation_id: str | None = None
    ) -> RenderResult:
        return await self.navigation.perform(
            self.key, "cancel", source=source, operation_id=self.operation_id(operation_id)
        )

    async def refresh(
        self,
        *,
        source: str = "application",
        operation_id: str | None = None,
        accepted_activity: bool = True,
    ) -> RenderResult:
        return await self.navigation.perform(
            self.key,
            "refresh",
            source=source,
            operation_id=self.operation_id(operation_id),
            accepted_activity=accepted_activity,
        )

    async def touch(
        self, *, source: str = "application", operation_id: str | None = None
    ) -> NavigationSnapshot:
        return await self.navigation.touch(
            self.key, source=source, operation_id=self.operation_id(operation_id)
        )

    async def prepare_action(
        self,
        kind: ActionKind,
        *,
        node_id: str | None = None,
        params: Mapping[str, object] | None = None,
        history: HistoryMode = "push",
        operation_id: str | None = None,
        source: str = "application",
        accepted_activity: bool = True,
    ) -> PreparedAction:
        return await self.navigation.prepare_action(
            self.key,
            kind,
            node_id=node_id,
            params=params,
            history=history,
            operation_id=self.operation_id(operation_id),
            source=source,
            accepted_activity=accepted_activity,
        )

    async def prepare_render(
        self,
        node_id: str,
        *,
        params: Mapping[str, object] | None = None,
        operation_id: str | None = None,
        source: str = "application",
    ) -> PreparedAction:
        return await self.navigation.prepare(
            self.key,
            node_id,
            params=params,
            operation_id=self.operation_id(operation_id),
            source=source,
        )

    async def complete_render(
        self, prepared: PreparedAction, *, rendered: RenderResult
    ) -> NavigationSnapshot:
        if prepared.key != self.key:
            raise ConfigurationError("The prepared action belongs to another conversation")
        return await self.navigation.complete(prepared, rendered=rendered)

    async def track(
        self,
        node_id: str,
        *,
        params: Mapping[str, object] | None = None,
        rendered: RenderResult,
        operation_id: str | None = None,
        source: str = "application",
    ) -> NavigationSnapshot:
        return await self.navigation.track(
            self.key,
            node_id,
            params=params,
            rendered=rendered,
            operation_id=self.operation_id(operation_id),
            source=source,
        )
