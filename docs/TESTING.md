# Testing

This document explains the testing approach for aiogram-sentinel and provides examples for testing your own implementations.

## Overview

aiogram-sentinel uses a comprehensive testing strategy that covers:

- **Unit tests**: Individual component testing
- **Integration tests**: End-to-end workflow testing
- **Performance tests**: Load and latency testing
- **Mock testing**: Isolated component testing

## Testing Framework

### Dependencies

```bash
# Install testing dependencies
pip install pytest pytest-asyncio pytest-mock
```

### Test Structure

```
tests/
├── unit/
│   ├── test_storage/
│   │   ├── test_memory.py
│   │   └── test_redis.py
│   ├── test_middlewares/
│   │   ├── test_blocking.py
│   │   ├── test_auth.py
│   │   ├── test_debouncing.py
│   │   └── test_throttling.py
│   └── test_utils/
│       └── test_keys.py
├── integration/
│   ├── test_setup.py
│   └── test_workflows.py
└── performance/
    ├── test_load.py
    └── test_latency.py
```

## Unit Testing

### Storage Backend Testing

#### Memory Backend Tests

```python
import pytest
import asyncio
from aiogram_sentinel.storage.memory import MemoryRateLimiter

@pytest.mark.asyncio
async def test_memory_rate_limiter():
    """Test memory rate limiter functionality."""
    limiter = MemoryRateLimiter()
    
    # Test increment
    count = await limiter.increment_rate_limit("user:123", 60)
    assert count == 1
    
    # Test multiple increments
    count = await limiter.increment_rate_limit("user:123", 60)
    assert count == 2
    
    # Test get current count
    current = await limiter.get_rate_limit("user:123")
    assert current == 2
    
    # Test reset
    await limiter.reset_rate_limit("user:123")
    current = await limiter.get_rate_limit("user:123")
    assert current == 0

@pytest.mark.asyncio
async def test_memory_rate_limiter_window():
    """Test rate limiter window functionality."""
    limiter = MemoryRateLimiter()
    
    # Add timestamps
    await limiter.increment_rate_limit("user:123", 1)  # 1 second window
    await limiter.increment_rate_limit("user:123", 1)
    
    # Should have 2 requests
    count = await limiter.get_rate_limit("user:123")
    assert count == 2
    
    # Wait for window to expire
    await asyncio.sleep(1.1)
    
    # Should have 0 requests (window expired)
    count = await limiter.get_rate_limit("user:123")
    assert count == 0
```

#### Redis Backend Tests

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram_sentinel.storage.redis import RedisRateLimiter

@pytest.mark.asyncio
async def test_redis_rate_limiter():
    """Test Redis rate limiter functionality."""
    # Mock Redis connection
    mock_redis = AsyncMock()
    mock_redis.pipeline.return_value = AsyncMock()
    
    # Mock pipeline execution
    mock_pipeline = mock_redis.pipeline.return_value
    mock_pipeline.incr.return_value = None
    mock_pipeline.expire.return_value = None
    mock_pipeline.execute.return_value = [5, 1]  # [incr_result, expire_result]
    
    limiter = RedisRateLimiter(mock_redis, "test:")
    
    # Test increment
    count = await limiter.increment_rate_limit("user:123", 60)
    assert count == 5
    
    # Verify Redis calls
    mock_redis.pipeline.assert_called_once()
    mock_pipeline.incr.assert_called_once_with("test:rate:user:123")
    mock_pipeline.expire.assert_called_once_with("test:rate:user:123", 60, nx=True)
    mock_pipeline.execute.assert_called_once()
```

### Middleware Testing

#### Blocking Middleware Tests

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram_sentinel.middlewares.blocking import BlockingMiddleware

@pytest.mark.asyncio
async def test_blocking_middleware():
    """Test blocking middleware functionality."""
    # Mock blocklist backend
    mock_blocklist = AsyncMock()
    mock_blocklist.is_blocked.return_value = False
    
    middleware = BlockingMiddleware(mock_blocklist)
    
    # Mock handler
    mock_handler = AsyncMock()
    mock_handler.return_value = "handler_result"
    
    # Mock event
    mock_event = MagicMock()
    mock_event.from_user.id = 123
    
    # Mock data
    data = {}
    
    # Test non-blocked user
    result = await middleware(mock_handler, mock_event, data)
    assert result == "handler_result"
    assert "sentinel_blocked" not in data
    
    # Test blocked user
    mock_blocklist.is_blocked.return_value = True
    result = await middleware(mock_handler, mock_event, data)
    assert result is None
    assert data["sentinel_blocked"] is True
    mock_handler.assert_called_once()  # Only called once (first test)
```

#### Auth Middleware Tests

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram_sentinel.middlewares.auth import AuthMiddleware

@pytest.mark.asyncio
async def test_auth_middleware():
    """Test auth middleware functionality."""
    # Mock user repo
    mock_user_repo = AsyncMock()
    mock_user_repo.is_registered.return_value = True
    
    middleware = AuthMiddleware(mock_user_repo)
    
    # Mock handler
    mock_handler = AsyncMock()
    mock_handler.return_value = "handler_result"
    
    # Mock event
    mock_event = MagicMock()
    mock_event.from_user.id = 123
    mock_event.from_user.username = "testuser"
    
    # Mock data
    data = {}
    
    # Test successful auth
    result = await middleware(mock_handler, mock_event, data)
    assert result == "handler_result"
    assert data["user_exists"] is True
    
    # Test with @require_registered decorator
    mock_handler._sentinel_require_registered = True
    mock_user_repo.is_registered.return_value = False
    
    result = await middleware(mock_handler, mock_event, data)
    assert result is None
    assert data["sentinel_auth_required"] is True
```

### Decorator Testing

```python
import pytest
from aiogram_sentinel.decorators import rate_limit, debounce, require_registered

def test_rate_limit_decorator():
    """Test rate limit decorator."""
    @rate_limit(limit=5, window=30)
    async def test_handler():
        return "test"
    
    # Check decorator sets attribute
    assert hasattr(test_handler, "_sentinel_rate_limit")
    config = getattr(test_handler, "_sentinel_rate_limit")
    assert config["limit"] == 5
    assert config["window"] == 30

def test_debounce_decorator():
    """Test debounce decorator."""
    @debounce(delay=2.0)
    async def test_handler():
        return "test"
    
    # Check decorator sets attribute
    assert hasattr(test_handler, "_sentinel_debounce")
    config = getattr(test_handler, "_sentinel_debounce")
    assert config["delay"] == 2.0

def test_require_registered_decorator():
    """Test require registered decorator."""
    @require_registered()
    async def test_handler():
        return "test"
    
    # Check decorator sets attribute
    assert hasattr(test_handler, "_sentinel_require_registered")
    assert getattr(test_handler, "_sentinel_require_registered") is True
```

## Integration Testing

### Setup Testing

```python
import pytest
from aiogram import Dispatcher
from aiogram_sentinel import Sentinel, SentinelConfig

@pytest.mark.asyncio
async def test_sentinel_setup():
    """Test complete Sentinel setup."""
    # Create dispatcher
    dp = Dispatcher()
    
    # Configure
    config = SentinelConfig(backend="memory")
    
    # Setup
    router, backends = Sentinel.setup(dp, config)
    
    # Verify setup
    assert router is not None
    assert backends is not None
    assert backends.rate_limiter is not None
    assert backends.debounce is not None
    assert backends.blocklist is not None
    assert backends.user_repo is not None

@pytest.mark.asyncio
async def test_sentinel_setup_with_hooks():
    """Test Sentinel setup with custom hooks."""
    # Mock hooks
    mock_rate_limit_hook = AsyncMock()
    mock_resolve_user = AsyncMock()
    mock_block_hook = AsyncMock()
    mock_unblock_hook = AsyncMock()
    
    # Create dispatcher
    dp = Dispatcher()
    
    # Configure
    config = SentinelConfig(backend="memory")
    
    # Setup with hooks
    router, backends = Sentinel.setup(
        dp, config,
        on_rate_limited=mock_rate_limit_hook,
        resolve_user=mock_resolve_user,
        on_block=mock_block_hook,
        on_unblock=mock_unblock_hook,
    )
    
    # Verify setup
    assert router is not None
    assert backends is not None
```

### Workflow Testing

```python
import pytest
from aiogram import Dispatcher
from aiogram.types import Message, User
from aiogram_sentinel import Sentinel, SentinelConfig

@pytest.mark.asyncio
async def test_complete_workflow():
    """Test complete event processing workflow."""
    # Setup
    dp = Dispatcher()
    config = SentinelConfig(backend="memory")
    router, backends = Sentinel.setup(dp, config)
    
    # Mock message
    mock_user = User(id=123, is_bot=False, first_name="Test")
    mock_message = Message(
        message_id=1,
        date=1234567890,
        chat=MagicMock(),
        from_user=mock_user,
        text="/test"
    )
    
    # Mock handler
    mock_handler = AsyncMock()
    mock_handler.return_value = "success"
    
    # Test workflow
    data = {}
    
    # Process through middleware chain
    # (This would be done by aiogram in real usage)
    result = await mock_handler(mock_message, data)
    
    # Verify result
    assert result == "success"
```

## Performance Testing

### Load Testing

```python
import pytest
import asyncio
import time
from aiogram_sentinel.storage.memory import MemoryRateLimiter

@pytest.mark.asyncio
async def test_rate_limiter_performance():
    """Test rate limiter performance under load."""
    limiter = MemoryRateLimiter()
    
    # Test concurrent increments
    async def increment_user(user_id):
        for _ in range(100):
            await limiter.increment_rate_limit(f"user:{user_id}", 60)
    
    # Run 10 concurrent users
    start_time = time.time()
    await asyncio.gather(*[increment_user(i) for i in range(10)])
    end_time = time.time()
    
    # Should complete in reasonable time
    assert (end_time - start_time) < 1.0  # Less than 1 second
    
    # Verify counts
    for i in range(10):
        count = await limiter.get_rate_limit(f"user:{i}")
        assert count == 100

@pytest.mark.asyncio
async def test_middleware_latency():
    """Test middleware processing latency."""
    from aiogram_sentinel.middlewares.blocking import BlockingMiddleware
    
    # Mock blocklist
    mock_blocklist = AsyncMock()
    mock_blocklist.is_blocked.return_value = False
    
    middleware = BlockingMiddleware(mock_blocklist)
    
    # Mock handler
    mock_handler = AsyncMock()
    mock_handler.return_value = "result"
    
    # Mock event
    mock_event = MagicMock()
    mock_event.from_user.id = 123
    
    # Measure latency
    start_time = time.time()
    for _ in range(1000):
        await middleware(mock_handler, mock_event, {})
    end_time = time.time()
    
    # Calculate average latency
    avg_latency = (end_time - start_time) / 1000
    assert avg_latency < 0.001  # Less than 1ms per request
```

## Mock Testing

### External Dependencies

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_redis_connection_failure():
    """Test Redis connection failure handling."""
    with patch('redis.asyncio.Redis') as mock_redis_class:
        # Mock connection failure
        mock_redis_class.from_url.side_effect = Exception("Connection failed")
        
        from aiogram_sentinel.storage.factory import build_backends
        from aiogram_sentinel import SentinelConfig
        
        config = SentinelConfig(backend="redis", redis_url="redis://invalid")
        
        # Should raise ConfigurationError
        with pytest.raises(Exception):
            build_backends(config)

@pytest.mark.asyncio
async def test_hook_failure_handling():
    """Test hook failure doesn't break middleware."""
    # Mock failing hook
    async def failing_hook(event, data, retry_after):
        raise Exception("Hook failed")
    
    # Mock successful hook
    async def successful_hook(event, data):
        return {"user_id": 123}
    
    # Setup with mixed hooks
    dp = Dispatcher()
    config = SentinelConfig(backend="memory")
    
    router, backends = Sentinel.setup(
        dp, config,
        on_rate_limited=failing_hook,
        resolve_user=successful_hook,
    )
    
    # Should not raise exception
    assert router is not None
    assert backends is not None
```

## Test Configuration

### pytest.ini

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --disable-warnings
markers =
    unit: Unit tests
    integration: Integration tests
    performance: Performance tests
    slow: Slow tests
asyncio_mode = auto
```

### conftest.py

```python
import pytest
import asyncio
from aiogram_sentinel.storage.memory import (
    MemoryRateLimiter,
    MemoryDebounce,
    MemoryBlocklist,
    MemoryUserRepo,
)

@pytest.fixture
def memory_backends():
    """Provide memory backends for testing."""
    return {
        "rate_limiter": MemoryRateLimiter(),
        "debounce": MemoryDebounce(),
        "blocklist": MemoryBlocklist(),
        "user_repo": MemoryUserRepo(),
    }

@pytest.fixture
def mock_event():
    """Provide mock Telegram event."""
    from unittest.mock import MagicMock
    from aiogram.types import User, Message
    
    user = User(id=123, is_bot=False, first_name="Test")
    message = Message(
        message_id=1,
        date=1234567890,
        chat=MagicMock(),
        from_user=user,
        text="/test"
    )
    return message

@pytest.fixture
def mock_handler():
    """Provide mock handler."""
    from unittest.mock import AsyncMock
    return AsyncMock(return_value="success")
```

## Running Tests

### Basic Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_storage/test_memory.py

# Run with coverage
pytest --cov=aiogram_sentinel

# Run specific test
pytest tests/unit/test_storage/test_memory.py::test_memory_rate_limiter
```

### Advanced Testing

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run performance tests
pytest -m performance

# Run with verbose output
pytest -v

# Run in parallel
pytest -n auto

# Run with specific Python version
python -m pytest
```

## Continuous Integration

### GitHub Actions

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.10, 3.11, 3.12]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .[dev]
    
    - name: Run tests
      run: |
        pytest --cov=aiogram_sentinel --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

## Best Practices

### 1. Test Organization

- **Group related tests**: Use classes and modules
- **Descriptive names**: Clear test function names
- **One concept per test**: Test one thing at a time
- **Arrange-Act-Assert**: Clear test structure

### 2. Mocking

- **Mock external dependencies**: Databases, APIs, etc.
- **Use AsyncMock for async functions**: Proper async mocking
- **Verify interactions**: Check mock calls and arguments
- **Reset mocks**: Clean state between tests

### 3. Async Testing

- **Use pytest-asyncio**: Proper async test support
- **Await async operations**: Don't forget await
- **Test timeouts**: Use asyncio.wait_for for timeout testing
- **Clean up resources**: Close connections, cancel tasks

### 4. Performance Testing

- **Measure what matters**: Latency, throughput, memory
- **Use realistic data**: Test with production-like data
- **Set performance baselines**: Define acceptable limits
- **Monitor regressions**: Track performance over time

### 5. Integration Testing

- **Test complete workflows**: End-to-end scenarios
- **Use real components**: Minimal mocking
- **Test error scenarios**: Failure cases and recovery
- **Verify side effects**: Check data changes, logs, etc.
