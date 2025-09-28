# ADR-0002: Storage Backend Architecture

**Status**: Accepted  
**Date**: 2024-09-28  
**Authors**: ArmanAvanesyan  

## Context

aiogram-sentinel requires persistent storage for protection data (rate limits, user blocks, debounce state, user registry). The storage system must support both development and production use cases with different performance and persistence requirements.

Key requirements:
- Support multiple storage implementations
- Development-friendly (no external dependencies)
- Production-ready (persistent, scalable)
- Protocol-based design for extensibility
- Type-safe interfaces

## Decision

We will implement a protocol-based storage architecture with multiple backend implementations:

**Storage Protocols**:
- `RateLimiterBackend`: Rate limiting operations
- `DebounceBackend`: Debounce state management
- `BlocklistBackend`: User blocking operations
- `UserRepo`: User registration and data

**Backend Implementations**:
- `MemoryStorage`: In-memory storage for development
- `RedisStorage`: Redis-based storage for production

**Storage Factory**:
- `StorageFactory`: Creates all backend instances from a single storage config

## Alternatives Considered

### 1. Single Storage Interface

**Pros**: Simpler, single interface to implement
**Cons**: Large interface, violates interface segregation principle

**Rejected**: Would force implementations to support features they don't need

### 2. Database-First Approach (PostgreSQL/SQLite)

**Pros**: ACID transactions, complex queries, familiar to many developers
**Cons**: Heavier dependencies, overkill for simple key-value operations

**Rejected**: Redis provides better performance for our use case

### 3. File-Based Storage

**Pros**: No external dependencies, simple deployment
**Cons**: Poor concurrency, limited scalability, platform-dependent

**Rejected**: Not suitable for production use

### 4. Abstract Base Classes Instead of Protocols

**Pros**: Can provide default implementations
**Cons**: Inheritance-based, less flexible than protocols

**Rejected**: Protocols are more Pythonic and flexible

## Consequences

### Positive

- **Flexibility**: Easy to add new storage backends
- **Development Friendly**: Memory storage requires no setup
- **Production Ready**: Redis storage handles scale
- **Type Safety**: Protocols provide clear contracts
- **Testing**: Easy to mock storage interfaces
- **Performance**: Each backend optimized for its use case

### Negative

- **Complexity**: Multiple protocols to understand
- **Consistency**: No ACID transactions across different data types
- **Dependencies**: Redis backend requires Redis server

### Risks

- **Data Loss**: Memory backend loses data on restart
- **Redis Dependency**: Production deployments must manage Redis
- **Protocol Evolution**: Changes to protocols affect all implementations

## Implementation Details

### Protocol Design

```python
from typing import Protocol

class RateLimiterBackend(Protocol):
    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool:
        """Check if operation is allowed and increment counter."""
    
    async def get_rate_limit(self, key: str) -> int:
        """Get current count for a key."""
    
    async def increment_rate_limit(self, key: str, per_seconds: int) -> int:
        """Increment counter and return new count."""
```

### Memory Implementation

```python
class MemoryRateLimiter:
    def __init__(self):
        self._counters: dict[str, list[float]] = {}
    
    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool:
        now = time.time()
        if key not in self._counters:
            self._counters[key] = []
        
        # Clean old entries
        cutoff = now - per_seconds
        self._counters[key] = [t for t in self._counters[key] if t > cutoff]
        
        # Check limit
        if len(self._counters[key]) >= max_events:
            return False
        
        # Add new entry
        self._counters[key].append(now)
        return True
```

### Redis Implementation

```python
class RedisRateLimiter:
    def __init__(self, redis: Redis, namespace: str = "rate_limit"):
        self._redis = redis
        self._namespace = namespace
    
    async def allow(self, key: str, max_events: int, per_seconds: int) -> bool:
        redis_key = f"{self._namespace}:{key}"
        
        async with self._redis.pipeline() as pipe:
            pipe.zremrangebyscore(redis_key, 0, time.time() - per_seconds)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {str(time.time()): time.time()})
            pipe.expire(redis_key, per_seconds)
            results = await pipe.execute()
        
        current_count = results[1]
        return current_count < max_events
```

### Storage Factory

```python
class StorageFactory:
    @staticmethod
    def create_backends(storage_config: StorageConfig) -> tuple[...]:
        if isinstance(storage_config, MemoryStorageConfig):
            return (
                MemoryRateLimiter(),
                MemoryDebounce(),
                MemoryBlocklist(),
                MemoryUserRepo(),
            )
        elif isinstance(storage_config, RedisStorageConfig):
            redis = Redis.from_url(storage_config.url)
            return (
                RedisRateLimiter(redis, storage_config.namespace),
                RedisDebounce(redis, storage_config.namespace),
                RedisBlocklist(redis, storage_config.namespace),
                RedisUserRepo(redis, storage_config.namespace),
            )
```

## Data Models

### Rate Limiting

**Memory**: `dict[str, list[float]]` - Key to list of timestamps
**Redis**: Sorted sets with timestamps as scores

### Debouncing

**Memory**: `dict[str, float]` - Key to expiration timestamp
**Redis**: Keys with TTL

### Blocklist

**Memory**: `set[int]` - Set of blocked user IDs
**Redis**: Set data structure

### User Repository

**Memory**: `dict[int, dict[str, Any]]` - User ID to user data
**Redis**: Hash data structure per user

## Performance Characteristics

| Backend | Setup | Throughput | Memory | Persistence | Scalability |
|---------|-------|------------|--------|-------------|-------------|
| Memory | None | 1M+ ops/sec | High | None | Single instance |
| Redis | Redis server | 50K ops/sec | Low | Full | Horizontal |

## Testing Strategy

### Protocol Compliance Tests

```python
async def test_rate_limiter_protocol(backend: RateLimiterBackend):
    """Test that backend implements protocol correctly."""
    # Test allow/deny logic
    assert await backend.allow("key1", 1, 60) == True
    assert await backend.allow("key1", 1, 60) == False
    
    # Test get_rate_limit
    count = await backend.get_rate_limit("key1")
    assert count == 1
```

### Backend-Specific Tests

```python
class TestMemoryRateLimiter:
    async def test_memory_cleanup(self):
        # Test memory-specific behavior
        pass

class TestRedisRateLimiter:
    async def test_redis_expiration(self):
        # Test Redis-specific behavior
        pass
```

## Migration Path

### From Memory to Redis

```python
# Development
sentinel = Sentinel(storage=MemoryStorage())

# Production
sentinel = Sentinel(storage=RedisStorage("redis://localhost:6379"))
```

### Data Migration (Future)

```python
async def migrate_data(source: StorageBackend, target: StorageBackend):
    # Export data from source
    # Import data to target
    pass
```

## Future Storage Backends

### PostgreSQL Backend
- ACID transactions
- Complex queries
- Better for analytics

### SQLite Backend
- File-based persistence
- No external dependencies
- Good for small productions

### Distributed Cache Backend
- Multiple Redis instances
- Consistent hashing
- Geographic distribution

## Success Metrics

- **Performance**: Memory backend >500K ops/sec, Redis backend >20K ops/sec
- **Reliability**: 99.9% uptime for Redis backend
- **Adoption**: Community creates additional backends
- **Compatibility**: All backends pass protocol compliance tests

## References

- [Redis Data Structures](https://redis.io/docs/data-types/)
- [Python Protocols](https://docs.python.org/3/library/typing.html#typing.Protocol)
- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)

## Related ADRs

- ADR-0001: Middleware Architecture
- ADR-0003: Configuration System Design
- ADR-0005: Key Generation Strategy
