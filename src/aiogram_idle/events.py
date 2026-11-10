"""Observational events. Failures in subscribers never repeat business effects."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from .models import IdleEvent

logger = logging.getLogger(__name__)


EventSink = Callable[[IdleEvent], Awaitable[None]]


async def emit(sink: EventSink | None, event: IdleEvent) -> None:
    if sink is not None:
        try:
            await sink(event)
        except Exception:
            logger.warning("Idle event subscriber failed for outcome=%s", event.outcome)
