"""Task-preserving timeout scope, including Python 3.10."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import cast


@asynccontextmanager
async def bounded(seconds: float) -> AsyncGenerator[None, None]:
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("Timeout scope requires an asyncio task")
    cancelling = cast(Callable[[], int] | None, getattr(task, "cancelling", None))
    uncancel = cast(Callable[[], int] | None, getattr(task, "uncancel", None))
    baseline = cancelling() if cancelling is not None else 0
    expired = False
    consumed = False
    marker = object()
    legacy_marker = False
    legacy_previous: object = None

    def expire() -> None:
        nonlocal expired, legacy_marker, legacy_previous
        expired = True
        if cancelling is None:
            legacy_previous = getattr(task, "_cancel_message", None)
        task.cancel(marker)
        if cancelling is None and hasattr(task, "_cancel_message"):
            # CPython 3.10 has no cancellation counter. Pin its message so even
            # an external cancel(None) racing this cancellation remains distinct.
            # Other Task implementations fall back to the delivered marker.
            try:
                setattr(task, "_cancel_message", marker)  # noqa: B010 -- guarded 3.10-only attribute
            except (AttributeError, TypeError):
                pass
            else:
                legacy_marker = True

    def consume() -> int:
        nonlocal consumed
        if uncancel is not None and not consumed:
            consumed = True
            return uncancel()
        return cancelling() if cancelling is not None else 0

    handle = asyncio.get_running_loop().call_later(seconds, expire)
    try:
        yield
    except asyncio.CancelledError as exc:
        if expired:
            remaining = consume()
            owned = (
                remaining <= baseline
                if cancelling is not None
                else exc.args == (marker,)
                and (not legacy_marker or getattr(task, "_cancel_message", None) is marker)
            )
            if owned:
                raise asyncio.TimeoutError from exc
        raise
    finally:
        handle.cancel()
        if expired:
            if legacy_marker and getattr(task, "_cancel_message", None) is marker:
                # Restore an outer timeout marker, never an external cancellation.
                setattr(task, "_cancel_message", legacy_previous)  # noqa: B010
            # A body that suppresses CancelledError still must relinquish exactly
            # this timeout's request; external cancellation requests are retained.
            consume()
