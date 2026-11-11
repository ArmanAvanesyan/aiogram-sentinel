"""Explicit recovery reuses retained receipts, never a fabricated update."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import OperationPending
from .models import ConversationKey, RenderResult

if TYPE_CHECKING:
    from .navigation import Navigation


async def recover(nav: Navigation, key: ConversationKey, *, operation_id: str) -> RenderResult:
    from .actions import as_render, execute

    async with nav.coordinator.hold(key):
        status = await nav.repository.lookup_operation(key, operation_id=operation_id)
        if status.prepared is None:
            raise OperationPending("No retained action exists for this operation")
        prepared = status.prepared
        await nav.allowed(
            key, nav.registry.get(prepared.node_id), prepared.params, prepared.intent.source
        )
        if status.result is not None:
            return as_render(status.result.snapshot)
        return await execute(nav, prepared)
