"""Test configuration and fixtures for aiogram-sentinel."""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from aiogram_sentinel.storage.memory import (
    MemoryDebounce,
    MemoryRateLimiter,
)


@pytest.fixture
def mock_time():
    """Mock time.monotonic() for deterministic testing."""
    with patch("time.monotonic") as mock:
        mock.return_value = 1000.0
        yield mock


@pytest.fixture
def mock_time_advance():
    """Mock time.monotonic() that can be advanced for testing."""
    current_time = 1000.0

    def advance(seconds: float) -> None:
        nonlocal current_time
        current_time += seconds

    def get_time() -> float:
        return current_time

    with patch("time.monotonic", side_effect=get_time) as mock:
        mock.advance = advance
        yield mock


@pytest.fixture
def memory_backends():
    """Provide memory backends for testing."""
    return {
        "rate_limiter": MemoryRateLimiter(),
        "debounce": MemoryDebounce(),
    }


@pytest.fixture
def mock_user():
    """Create a mock Telegram user."""
    return User(
        id=12345,
        is_bot=False,
        first_name="Test",
        last_name="User",
        username="testuser",
        language_code="en",
    )


@pytest.fixture
def mock_bot_user():
    """Create a mock Telegram bot user."""
    return User(
        id=67890,
        is_bot=True,
        first_name="TestBot",
        username="testbot",
    )


@pytest.fixture
def mock_chat():
    """Create a mock Telegram chat."""
    return Chat(
        id=12345,
        type="private",
        username="testuser",
    )


@pytest.fixture
def mock_message(mock_user: User, mock_chat: Chat) -> Message:
    """Create a mock Telegram message."""
    from datetime import datetime

    return Message(
        message_id=1,
        date=datetime.fromtimestamp(int(time.time())),
        chat=mock_chat,
        from_user=mock_user,
        text="/test",
    )


@pytest.fixture
def mock_callback_query(mock_user: User, mock_chat: Chat) -> CallbackQuery:
    """Create a mock Telegram callback query."""
    return CallbackQuery(
        id="test_callback_id",
        from_user=mock_user,
        chat_instance="test_chat_instance",
        data="test_data",
    )


@pytest.fixture
def mock_handler() -> AsyncMock:
    """Create a mock async handler function."""
    return AsyncMock(return_value="handler_result")


@pytest.fixture
def mock_data() -> dict[str, Any]:
    """Create a mock middleware data dictionary."""
    return {}


@pytest.fixture
def rate_limiter() -> MemoryRateLimiter:
    """Create a MemoryRateLimiter instance."""
    return MemoryRateLimiter()


@pytest.fixture
def debounce() -> MemoryDebounce:
    """Create a MemoryDebounce instance."""
    return MemoryDebounce()


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock Redis connection."""
    mock_redis = AsyncMock()
    mock_redis.pipeline.return_value = AsyncMock()
    mock_pipeline = mock_redis.pipeline.return_value
    mock_pipeline.incr.return_value = None
    mock_pipeline.expire.return_value = None
    mock_pipeline.execute.return_value = [1, 1]
    return mock_redis


@pytest.fixture
def mock_rate_limiter() -> AsyncMock:
    """Create a mock rate limiter."""
    limiter = AsyncMock()
    limiter.increment_rate_limit.return_value = 1
    limiter.get_rate_limit.return_value = 0
    limiter.reset_rate_limit.return_value = None
    return limiter


@pytest.fixture
def mock_debounce_backend() -> AsyncMock:
    """Create a mock debounce backend."""
    backend = AsyncMock()
    backend.is_debounced.return_value = False
    backend.set_debounce.return_value = None
    return backend


@pytest.fixture
def mock_on_rate_limited() -> AsyncMock:
    """Create a mock on_rate_limited hook."""
    return AsyncMock()


# Performance test fixtures
@pytest.fixture
def performance_thresholds() -> dict[str, float]:
    """Define performance thresholds for tests."""
    return {
        "rate_limit_increment": 0.001,  # 1ms
        "debounce_check": 0.001,  # 1ms
        "middleware_overhead": 0.005,  # 5ms
    }


@pytest.fixture
def large_user_set() -> set[int]:
    """Create a large set of user IDs for performance testing."""
    return set(range(1000, 2000))


@pytest.fixture
def many_handlers() -> list[str]:
    """Create many handler names for performance testing."""
    return [f"handler_{i}" for i in range(100)]


# Async test configuration
@pytest.fixture(scope="session")
def event_loop() -> Any:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Test markers
def pytest_configure(config: Any) -> None:
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "perf: Performance tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow tests")


# Test collection
def pytest_collection_modifyitems(config: Any, items: Any) -> None:
    """Modify test collection to add markers."""
    for item in items:
        # Add unit marker to unit tests
        if "unit" in item.nodeid:
            item.add_marker(pytest.mark.unit)

        # Add perf marker to performance tests
        if "perf" in item.nodeid:
            item.add_marker(pytest.mark.perf)

        # Add slow marker to performance tests
        if "perf" in item.nodeid:
            item.add_marker(pytest.mark.slow)
