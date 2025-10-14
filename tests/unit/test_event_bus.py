"""Tests for the internal event bus."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiogram_sentinel.events import (
    BaseEvent,
    DebounceEvent,
    ErrorEvent,
    RateLimitEvent,
    SentinelEvents,
)


class MockEvent(BaseEvent):
    """Mock event class for testing."""

    def __init__(self, value: str) -> None:
        self.value = value


class TestSentinelEvents:
    """Test the SentinelEvents class."""

    def test_init(self) -> None:
        """Test event bus initialization."""
        bus = SentinelEvents()
        assert bus._subscribers == {}

    def test_subscribe(self) -> None:
        """Test subscribing to events."""
        bus = SentinelEvents()
        handler = AsyncMock()

        bus.subscribe(MockEvent, handler)

        assert MockEvent in bus._subscribers
        assert handler in bus._subscribers[MockEvent]

    def test_subscribe_multiple_handlers(self) -> None:
        """Test subscribing multiple handlers to same event type."""
        bus = SentinelEvents()
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        bus.subscribe(MockEvent, handler1)
        bus.subscribe(MockEvent, handler2)

        assert len(bus._subscribers[MockEvent]) == 2
        assert handler1 in bus._subscribers[MockEvent]
        assert handler2 in bus._subscribers[MockEvent]

    def test_publish_no_subscribers(self) -> None:
        """Test publishing with no subscribers."""
        bus = SentinelEvents()
        event = MockEvent("test")

        # Should not raise
        bus.publish(event)

    @patch("asyncio.create_task")
    def test_publish_with_subscribers(self, mock_create_task: MagicMock) -> None:
        """Test publishing with subscribers."""
        bus = SentinelEvents()
        handler = AsyncMock()
        bus.subscribe(MockEvent, handler)

        event = MockEvent("test")
        bus.publish(event)

        # Should create tasks for subscribers
        assert mock_create_task.called

    async def test_safe_handle_success(self) -> None:
        """Test safe handling of successful handler."""
        bus = SentinelEvents()
        handler = AsyncMock()
        event = MockEvent("test")

        await bus._safe_handle(handler, event)

        handler.assert_called_once_with(event)

    async def test_safe_handle_exception(self) -> None:
        """Test safe handling of handler exception."""
        bus = SentinelEvents()
        handler = AsyncMock(side_effect=Exception("test error"))
        event = MockEvent("test")

        # Should not raise
        await bus._safe_handle(handler, event)

        handler.assert_called_once_with(event)


class MockEventClasses:
    """Test event dataclasses."""

    def test_error_event(self) -> None:
        """Test ErrorEvent creation."""
        event = ErrorEvent(
            error_type="test_error",
            error_message="Test error message",
            event_type="message",
            user_id=123,
            chat_id=456,
            locale="en",
            retry_after=5.0,
        )

        assert event.error_type == "test_error"
        assert event.error_message == "Test error message"
        assert event.event_type == "message"
        assert event.user_id == 123
        assert event.chat_id == 456
        assert event.locale == "en"
        assert event.retry_after == 5.0

    def test_rate_limit_event(self) -> None:
        """Test RateLimitEvent creation."""
        event = RateLimitEvent(
            user_id=123,
            chat_id=456,
            handler_name="test_handler",
            retry_after=10.0,
            scope="user",
        )

        assert event.user_id == 123
        assert event.chat_id == 456
        assert event.handler_name == "test_handler"
        assert event.retry_after == 10.0
        assert event.scope == "user"

    def test_debounce_event(self) -> None:
        """Test DebounceEvent creation."""
        event = DebounceEvent(
            user_id=123,
            chat_id=456,
            handler_name="test_handler",
            fingerprint="abc123",
            window=5,
        )

        assert event.user_id == 123
        assert event.chat_id == 456
        assert event.handler_name == "test_handler"
        assert event.fingerprint == "abc123"
        assert event.window == 5


@pytest.mark.asyncio
async def test_full_publish_flow() -> None:
    """Test the full publish flow with real handlers."""
    bus = SentinelEvents()
    handler1 = AsyncMock()
    handler2 = AsyncMock()

    bus.subscribe(MockEvent, handler1)
    bus.subscribe(MockEvent, handler2)

    event = MockEvent("test")
    bus.publish(event)

    # Wait for all tasks to complete
    await bus.wait_for_tasks()

    handler1.assert_called_once_with(event)
    handler2.assert_called_once_with(event)


async def test_wait_for_tasks() -> None:
    """Test waiting for tasks to complete."""
    bus = SentinelEvents()
    handler = AsyncMock()

    bus.subscribe(MockEvent, handler)

    event = MockEvent("test")
    bus.publish(event)

    # Wait for tasks to complete
    await bus.wait_for_tasks()

    handler.assert_called_once_with(event)
    assert len(bus._tasks) == 0  # All tasks should be cleaned up
