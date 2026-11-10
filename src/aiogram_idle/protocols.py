"""Extension contracts that do not import navigation or persistence drivers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Protocol, TypeVar

from .models import (
    ActionReceipt,
    FlowContext,
    FlowEligibility,
    IdleConversationKey,
    SessionSnapshot,
)

if TYPE_CHECKING:
    from .presentation import DeliveryReceipt, FinishRequest, PromptReceipt, PromptRequest

T = TypeVar("T")


class EffectRecorder(Protocol):
    async def run(
        self, stage: str, effect: Callable[[], Awaitable[T]], *, replay_safe: bool = False
    ) -> T: ...


class FlowAdapter(Protocol):
    async def inspect(self, context: FlowContext) -> FlowEligibility: ...
    async def resume(self, context: FlowContext, *, operation_id: str) -> ActionReceipt: ...
    async def abandon(
        self,
        context: FlowContext,
        *,
        reason: str,
        operation_id: str,
    ) -> ActionReceipt: ...
    async def restore(
        self,
        context: FlowContext,
        *,
        reason: str,
        operation_id: str,
    ) -> ActionReceipt: ...


class PromptPresenter(Protocol):
    async def show(self, request: PromptRequest) -> PromptReceipt: ...
    async def finish(self, request: FinishRequest) -> DeliveryReceipt: ...
    async def strip(self, receipt: PromptReceipt) -> DeliveryReceipt: ...


class Coordinator(Protocol):
    @property
    def active_scopes(self) -> int: ...
    def scope_token(self, key: IdleConversationKey) -> object | None: ...
    def scope_active(self, token: object) -> bool: ...
    def scope_matches(self, key: IdleConversationKey, token: object) -> bool: ...
    def hold(self, key: IdleConversationKey) -> AbstractAsyncContextManager[None]: ...


class SessionAuthority(Protocol):
    async def authorize(
        self,
        key: IdleConversationKey,
        session_id: str,
    ) -> SessionSnapshot: ...
