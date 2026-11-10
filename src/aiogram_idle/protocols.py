"""Extension contracts that do not import navigation or persistence drivers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, TypeVar

from aiogram_coordination import Coordinator as Coordinator
from aiogram_coordination import SessionAuthority as SessionAuthority

from .models import (
    ActionReceipt,
    FlowContext,
    FlowEligibility,
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
