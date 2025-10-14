"""Internal event bus for aiogram-sentinel."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BaseEvent:
    """Base class for all events."""

    pass


@dataclass
class ErrorEvent(BaseEvent):
    """Event emitted when an error occurs."""

    error_type: str
    error_message: str
    event_type: str
    user_id: int | None
    chat_id: int | None
    locale: str
    retry_after: float | None = None


@dataclass
class RateLimitEvent(BaseEvent):
    """Event emitted when rate limit is exceeded."""

    user_id: int | None
    chat_id: int | None
    handler_name: str
    retry_after: float
    scope: str


@dataclass
class DebounceEvent(BaseEvent):
    """Event emitted when message is debounced."""

    user_id: int | None
    chat_id: int | None
    handler_name: str
    fingerprint: str
    window: int


class SentinelEvents:
    """Internal event bus for aiogram-sentinel."""

    def __init__(self) -> None:
        """Initialize the event bus."""
        self._subscribers: defaultdict[
            type[BaseEvent], list[Callable[[BaseEvent], Awaitable[None]]]
        ] = defaultdict(list)
        self._tasks: set[asyncio.Task[None]] = set()

    def subscribe(
        self,
        event_type: type[BaseEvent],
        handler: Callable[[BaseEvent], Awaitable[None]],
    ) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: Type of event to subscribe to
            handler: Async handler function
        """
        self._subscribers[event_type].append(handler)

    def publish(self, event: BaseEvent) -> None:
        """Publish an event to all subscribers.

        Args:
            event: Event to publish
        """
        # Get all subscribers for this event type
        subscribers = self._subscribers.get(type(event), [])

        if not subscribers:
            return

        # Create tasks for all subscribers
        for handler in subscribers:
            task = asyncio.create_task(self._safe_handle(handler, event))
            # Add task to set for cleanup
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
 
        # Clean up completed tasks to prevent accumulation
        self._cleanup_completed_tasks()

    def _cleanup_completed_tasks(self) -> None:
        """Clean up completed tasks to prevent accumulation."""
        # Remove completed tasks from the set
        completed_tasks = {task for task in self._tasks if task.done()}
        self._tasks -= completed_tasks

    async def wait_for_tasks(self) -> None:
        """Wait for all active tasks to complete.

        This is useful for tests to ensure all event handlers have completed.
        """
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

    async def _safe_handle(
        self,
        handler: Callable[[BaseEvent], Awaitable[None]],
        event: BaseEvent,
    ) -> None:
        """Safely handle an event with a subscriber.

        Args:
            handler: Handler function
            event: Event to handle
        """
        try:
            await handler(event)
        except Exception as e:
            logger.exception("Event handler failed: %s", e)


# Global event bus instance
events = SentinelEvents()


def cleanup_events() -> None:
    """Clean up the global events instance.
    
    This is useful for tests to ensure no tasks are left running.
    """
    events._tasks.clear()
