"""Observational events. Failures in subscribers never repeat business effects."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from enum import Enum

from .models import IdleEvent

logger = logging.getLogger(__name__)


EventSink = Callable[[IdleEvent], Awaitable[None]]


class IdleOutcome(str, Enum):
    """Stable observational outcomes; wire values remain ordinary strings."""

    SHOWN = "shown"
    CONTINUED = "continued"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    RESTORED = "restored"
    DELIVERY_UNKNOWN = "delivery_unknown"
    FAILED = "failed"
    SESSION_EXPIRED = "session_expired"


def coarse_event_sink(
    sink: Callable[[str], Awaitable[None]], *, outcomes: dict[str, str]
) -> EventSink:
    """Forward application-selected coarse values without conversation identifiers."""
    mapping = dict(outcomes)
    if any(not key or not value for key, value in mapping.items()):
        raise ValueError("Outcome mappings must contain nonempty strings")

    async def observe(event: IdleEvent) -> None:
        value = mapping.get(event.outcome)
        if value is not None:
            await sink(value)

    return observe


async def emit(sink: EventSink | None, event: IdleEvent) -> None:
    if sink is not None:
        try:
            await sink(event)
        except Exception:
            logger.warning("Idle event subscriber failed for outcome=%s", event.outcome)
