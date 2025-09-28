# ADR-0004: Error Handling Strategy

**Status**: Accepted  
**Date**: 2024-09-28  
**Authors**: ArmanAvanesyan  

## Context

aiogram-sentinel operates as middleware in the critical path of message processing. Error handling must balance reliability, debuggability, and security while ensuring that protection failures don't break the bot entirely.

Key requirements:
- Graceful degradation when protection services fail
- Clear error messages for developers
- No sensitive information leakage
- Proper logging for debugging
- Fail-safe defaults for production

## Decision

We will implement a defensive error handling strategy with the following principles:

**Error Categories**:
- `ConfigurationError`: Invalid configuration (fail fast)
- `StorageError`: Storage backend failures (graceful degradation)
- `MiddlewareError`: Middleware processing errors (continue with warnings)

**Error Handling Strategy**:
- **Configuration Errors**: Fail fast during initialization
- **Storage Errors**: Log and continue with permissive defaults
- **Middleware Errors**: Log error, allow message processing to continue
- **Network Errors**: Retry with exponential backoff

**Logging Strategy**:
- Structured logging with correlation IDs
- Different log levels for different error types
- No sensitive data in logs
- Performance metrics for error rates

## Alternatives Considered

### 1. Fail-Fast Strategy

**Pros**: Clear error visibility, forces proper handling
**Cons**: Bot becomes unavailable on any protection failure

**Rejected**: Too disruptive for production bots

### 2. Silent Failure Strategy

**Pros**: Bot continues working regardless of protection failures
**Cons**: Hard to debug, security issues may go unnoticed

**Rejected**: Poor debugging experience and security implications

### 3. Circuit Breaker Pattern

**Pros**: Automatic recovery, prevents cascade failures
**Cons**: Additional complexity, may mask ongoing issues

**Partially Adopted**: Used for storage backends but not middleware

### 4. Exception Propagation

**Pros**: Caller can decide how to handle errors
**Cons**: Requires every user to implement error handling

**Rejected**: Too much burden on library users

## Consequences

### Positive

- **Reliability**: Bot continues working even with protection failures
- **Debuggability**: Clear error messages and structured logging
- **Security**: No sensitive information in error messages
- **Observability**: Metrics and logging for monitoring
- **Developer Experience**: Clear guidance on error handling

### Negative

- **Complexity**: Multiple error handling paths
- **Performance**: Error handling overhead
- **Masking Issues**: Some errors might be hidden in graceful degradation

### Risks

- **Silent Failures**: Important errors might be missed
- **Log Spam**: Too much error logging
- **Resource Leaks**: Error paths might not clean up properly

## Implementation Details

### Custom Exception Hierarchy

```python
class SentinelError(Exception):
    """Base exception for all aiogram-sentinel errors."""
    pass

class ConfigurationError(SentinelError):
    """Raised when configuration is invalid."""
    pass

class StorageError(SentinelError):
    """Raised when storage operations fail."""
    
    def __init__(self, message: str, backend: str, operation: str, recoverable: bool = True):
        super().__init__(message)
        self.backend = backend
        self.operation = operation
        self.recoverable = recoverable

class MiddlewareError(SentinelError):
    """Raised when middleware processing fails."""
    
    def __init__(self, message: str, middleware: str, user_id: int = None):
        super().__init__(message)
        self.middleware = middleware
        self.user_id = user_id
```

### Configuration Error Handling

```python
class SentinelConfig:
    def __post_init__(self):
        """Validate configuration and fail fast on errors."""
        try:
            self._validate_throttling()
            self._validate_debounce()
            self._validate_blocklist()
        except ValueError as e:
            raise ConfigurationError(f"Invalid configuration: {e}") from e
    
    def _validate_throttling(self):
        if self.throttling_default_max <= 0:
            raise ValueError("throttling_default_max must be positive")
        
        if self.throttling_default_per_seconds <= 0:
            raise ValueError("throttling_default_per_seconds must be positive")
        
        if self.throttling_default_max > 10000:
            raise ValueError("throttling_default_max too high (max 10000)")
```

### Storage Error Handling

```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ResilientRateLimiter:
    """Rate limiter with graceful error handling."""
    
    def __init__(self, backend: RateLimiterBackend, fallback_allow: bool = True):
        self.backend = backend
        self.fallback_allow = fallback_allow
        self._error_count = 0
        self._last_error_time = 0
    
    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool:
        try:
            result = await self.backend.allow(key, max_events, per_seconds)
            self._reset_error_state()
            return result
            
        except Exception as e:
            self._handle_storage_error(e, "allow", key)
            return self.fallback_allow  # Graceful degradation
    
    def _handle_storage_error(self, error: Exception, operation: str, key: str):
        """Handle storage errors with proper logging and metrics."""
        self._error_count += 1
        current_time = time.time()
        
        # Rate limit error logging
        if current_time - self._last_error_time > 60:  # Log once per minute
            logger.error(
                "Storage operation failed",
                extra={
                    "backend": self.backend.__class__.__name__,
                    "operation": operation,
                    "error": str(error),
                    "error_count": self._error_count,
                    "key_hash": hashlib.sha256(key.encode()).hexdigest()[:8],  # No sensitive data
                }
            )
            self._last_error_time = current_time
        
        # Emit metrics
        metrics.increment('storage_errors', tags={
            'backend': self.backend.__class__.__name__,
            'operation': operation,
        })
```

### Middleware Error Handling

```python
class ThrottlingMiddleware:
    async def __call__(self, handler, event, data):
        try:
            # Check rate limit
            user_id = self._get_user_id(event)
            if user_id is None:
                return await handler(event, data)  # Continue without rate limiting
            
            key = self._generate_key(user_id, handler)
            max_events, per_seconds = self._get_rate_limit_config(handler, data)
            
            is_allowed = await self.rate_limiter.allow(key, max_events, per_seconds)
            
            if not is_allowed:
                # Call rate limit hook if configured
                if self.on_rate_limited:
                    try:
                        await self.on_rate_limited(user_id, max_events, per_seconds)
                    except Exception as e:
                        logger.warning(f"Rate limit hook failed: {e}")
                
                return  # Block the message
            
            return await handler(event, data)
            
        except Exception as e:
            # Log error but continue processing
            logger.error(
                "Throttling middleware error",
                extra={
                    "error": str(e),
                    "user_id": getattr(event, 'from_user', {}).get('id'),
                    "handler": handler.__name__,
                }
            )
            
            # Continue with message processing
            return await handler(event, data)
```

### Circuit Breaker for Storage

```python
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Any

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: int = 60
    success_threshold: int = 3

class CircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time < self.config.recovery_timeout:
                raise StorageError("Circuit breaker is open", "circuit_breaker", "call")
            else:
                self.state = CircuitState.HALF_OPEN
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        else:
            self.failure_count = 0
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
```

### Retry Logic

```python
import asyncio
from typing import TypeVar, Callable, Any

T = TypeVar('T')

async def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_multiplier: float = 2.0,
    *args,
    **kwargs
) -> T:
    """Retry function with exponential backoff."""
    
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if attempt == max_retries:
                break
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (backoff_multiplier ** attempt), max_delay)
            
            logger.debug(f"Retry attempt {attempt + 1}/{max_retries + 1} after {delay}s")
            await asyncio.sleep(delay)
    
    # All retries exhausted
    raise StorageError(
        f"Operation failed after {max_retries + 1} attempts: {last_exception}",
        "retry",
        "call",
        recoverable=False
    ) from last_exception
```

## Error Reporting and Logging

### Structured Logging

```python
import logging
import json
from typing import Dict, Any

class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def error(self, message: str, **kwargs):
        """Log error with structured data."""
        extra = {
            'level': 'error',
            'timestamp': time.time(),
            'correlation_id': self._get_correlation_id(),
            **kwargs
        }
        
        # Remove sensitive data
        extra = self._sanitize_log_data(extra)
        
        self.logger.error(message, extra=extra)
    
    def _sanitize_log_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive information from log data."""
        sensitive_keys = {'password', 'token', 'secret', 'key', 'auth'}
        
        sanitized = {}
        for key, value in data.items():
            if any(sensitive_word in key.lower() for sensitive_word in sensitive_keys):
                sanitized[key] = '***REDACTED***'
            elif isinstance(value, str) and len(value) > 100:
                sanitized[key] = value[:100] + '...'
            else:
                sanitized[key] = value
        
        return sanitized
```

### Error Metrics

```python
from typing import Dict
import time

class ErrorMetrics:
    def __init__(self):
        self._counters: Dict[str, int] = {}
        self._last_reset = time.time()
    
    def increment(self, error_type: str, tags: Dict[str, str] = None):
        """Increment error counter."""
        key = f"{error_type}:{':'.join(f'{k}={v}' for k, v in (tags or {}).items())}"
        self._counters[key] = self._counters.get(key, 0) + 1
    
    def get_error_rate(self, window_seconds: int = 300) -> Dict[str, float]:
        """Get error rates over time window."""
        current_time = time.time()
        if current_time - self._last_reset > window_seconds:
            rates = {k: v / window_seconds for k, v in self._counters.items()}
            self._counters.clear()
            self._last_reset = current_time
            return rates
        return {}

# Global metrics instance
metrics = ErrorMetrics()
```

## Testing Error Scenarios

### Error Injection for Testing

```python
class FaultyStorage:
    """Storage backend that injects errors for testing."""
    
    def __init__(self, backend, failure_rate: float = 0.1):
        self.backend = backend
        self.failure_rate = failure_rate
    
    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool:
        if random.random() < self.failure_rate:
            raise StorageError("Simulated storage failure", "test", "allow")
        
        return await self.backend.allow(key, max_events, per_seconds)
```

### Error Handling Tests

```python
async def test_storage_error_handling():
    """Test graceful degradation on storage errors."""
    faulty_storage = FaultyStorage(MemoryRateLimiter(), failure_rate=1.0)
    resilient_limiter = ResilientRateLimiter(faulty_storage, fallback_allow=True)
    
    # Should not raise exception
    result = await resilient_limiter.allow("test_key", 5, 60)
    assert result is True  # Fallback behavior
    
    # Check that error was logged
    assert "Storage operation failed" in caplog.text

async def test_middleware_error_recovery():
    """Test middleware continues processing on errors."""
    # Mock storage to raise exception
    with patch.object(rate_limiter, 'allow', side_effect=Exception("Test error")):
        # Message should still be processed
        result = await middleware(mock_handler, mock_event, mock_data)
        assert result is not None
        
        # Handler should have been called
        mock_handler.assert_called_once()
```

## Monitoring and Alerting

### Health Checks

```python
async def health_check() -> Dict[str, Any]:
    """Comprehensive health check for monitoring."""
    health = {
        "status": "healthy",
        "timestamp": time.time(),
        "checks": {}
    }
    
    # Check storage backends
    for name, backend in [("rate_limiter", rate_limiter), ("blocklist", blocklist)]:
        try:
            await backend.health_check()
            health["checks"][name] = {"status": "healthy"}
        except Exception as e:
            health["checks"][name] = {"status": "unhealthy", "error": str(e)}
            health["status"] = "degraded"
    
    # Check error rates
    error_rates = metrics.get_error_rate()
    if any(rate > 10 for rate in error_rates.values()):  # More than 10 errors/sec
        health["status"] = "degraded"
        health["high_error_rates"] = error_rates
    
    return health
```

### Alert Conditions

```python
# Example alerting thresholds
ALERT_CONDITIONS = {
    "high_error_rate": lambda rates: any(rate > 10 for rate in rates.values()),
    "storage_unavailable": lambda health: any(
        check["status"] == "unhealthy" 
        for check in health["checks"].values()
    ),
    "circuit_breaker_open": lambda cb: cb.state == CircuitState.OPEN,
}
```

## Success Metrics

- **Availability**: 99.9% uptime even with storage failures
- **Error Recovery**: 95% of errors recovered within 1 minute
- **Data Loss**: <0.1% of protection decisions lost during failures
- **Observability**: 100% of errors logged with proper context

## References

- [Resilience Patterns](https://docs.microsoft.com/en-us/azure/architecture/patterns/category/resiliency)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Structured Logging](https://www.structlog.org/)

## Related ADRs

- ADR-0001: Middleware Architecture
- ADR-0002: Storage Backend Architecture
- ADR-0003: Configuration System Design
