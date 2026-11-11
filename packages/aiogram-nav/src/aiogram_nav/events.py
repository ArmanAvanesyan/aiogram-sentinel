"""Observational hooks run only after a successful location commit."""

import logging
from collections.abc import Awaitable, Callable

from .models import NavigationEvent

EventHook = Callable[[NavigationEvent], Awaitable[None]]


async def emit(hook: EventHook | None, event: NavigationEvent) -> None:
    if hook is None:
        return
    try:
        await hook(event)
    except Exception:
        logging.getLogger(__name__).warning("Navigation observation hook failed after commit")
