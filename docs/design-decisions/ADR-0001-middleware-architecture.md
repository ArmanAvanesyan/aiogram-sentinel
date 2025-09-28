# ADR-0001: Middleware Architecture

**Status**: Accepted  
**Date**: 2024-09-28  
**Authors**: ArmanAvanesyan  

## Context

aiogram-sentinel needs to provide protection features for Telegram bots built with aiogram v3. The library must integrate seamlessly with existing aiogram applications while providing comprehensive protection against spam, abuse, and unwanted behavior.

Key requirements:
- Easy integration with existing aiogram bots
- Minimal performance overhead
- Flexible configuration
- Extensible architecture
- Type safety

## Decision

We will implement aiogram-sentinel as a collection of specialized middleware components that integrate with aiogram's middleware system.

**Core Architecture**:
1. **Modular Middleware**: Separate middleware for each protection feature
2. **Unified Interface**: Single `Sentinel` class to configure all middleware
3. **Storage Abstraction**: Protocol-based storage backends
4. **Configuration System**: Centralized configuration with per-handler overrides

**Middleware Components**:
- `ThrottlingMiddleware`: Rate limiting
- `DebouncingMiddleware`: Duplicate message prevention  
- `AuthMiddleware`: User registration and context
- `BlockingMiddleware`: User blocking

## Alternatives Considered

### 1. Single Monolithic Middleware

**Pros**: Simpler to understand, single point of configuration
**Cons**: Harder to extend, all-or-nothing approach, complex testing

**Rejected**: Violates single responsibility principle and reduces flexibility

### 2. Decorator-Only Approach

**Pros**: Very explicit, no global state
**Cons**: Repetitive, hard to apply globally, inconsistent protection

**Rejected**: Too verbose for common use cases

### 3. Event-Based System

**Pros**: Very flexible, loosely coupled
**Cons**: Complex to understand, harder to debug, performance overhead

**Rejected**: Adds unnecessary complexity for the core use cases

### 4. Subclassing Dispatcher

**Pros**: Deep integration, can override core behavior
**Cons**: Breaks compatibility, hard to upgrade, couples to aiogram internals

**Rejected**: Too invasive and fragile

## Consequences

### Positive

- **Easy Integration**: Single line to add protection to existing bots
- **Modular Design**: Users can enable only needed features
- **Extensible**: Easy to add new middleware or storage backends
- **Type Safe**: Full type annotations throughout
- **Testable**: Each component can be tested independently
- **Performance**: Minimal overhead, storage abstraction allows optimization

### Negative

- **Complexity**: Multiple middleware components to understand
- **Order Dependency**: Middleware order matters for some features
- **Memory Overhead**: Each middleware maintains some state

### Risks

- **aiogram Changes**: Breaking changes in aiogram middleware system
- **Performance**: Multiple middleware calls per message
- **Configuration Complexity**: Many configuration options to manage

## Implementation Details

### Middleware Registration

```python
# Single registration point
sentinel = Sentinel()
dp.message.middleware(sentinel.middleware)

# Individual middleware (advanced)
dp.message.middleware(ThrottlingMiddleware(config, storage))
```

### Storage Abstraction

```python
# Protocol-based design allows multiple implementations
class RateLimiterBackend(Protocol):
    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool: ...
    async def get_rate_limit(self, key: str) -> int: ...
```

### Configuration Override

```python
# Global configuration
config = SentinelConfig(throttling_default_max=5)

# Per-handler override
@dp.message(Command("admin"))
@sentinel_rate_limit(limit=20, window=60)
async def admin_handler(message: Message): ...
```

## Success Metrics

- **Adoption**: Number of bots using aiogram-sentinel
- **Performance**: <100µs overhead per message
- **Compatibility**: Works with all aiogram v3 features
- **Extensibility**: Community creates custom storage backends
- **Stability**: No breaking changes in middleware API

## Future Considerations

- **Distributed Mode**: Support for multiple bot instances
- **Metrics Integration**: Built-in metrics collection
- **Admin Interface**: Web UI for monitoring and configuration
- **Machine Learning**: AI-based spam detection
- **Protocol Extensions**: New storage backends (PostgreSQL, SQLite)

## References

- [aiogram Middleware Documentation](https://docs.aiogram.dev/en/latest/dispatcher/middlewares.html)
- [Python Protocols](https://docs.python.org/3/library/typing.html#typing.Protocol)
- [Middleware Pattern](https://en.wikipedia.org/wiki/Middleware)

## Related ADRs

- ADR-0002: Storage Backend Architecture
- ADR-0003: Configuration System Design
- ADR-0004: Error Handling Strategy
