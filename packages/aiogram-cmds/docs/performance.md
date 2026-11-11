# Performance Guide

This guide covers performance optimization techniques for aiogram-cmds.

## 📊 Performance Overview

aiogram-cmds is designed for high performance with:
- Efficient command building algorithms
- Minimal API calls to Telegram
- Cached profile resolutions
- Batch operations where possible
- Optimized data structures

## 🚀 Optimization Techniques

### 1. Profile Resolution Caching

Cache profile resolutions to avoid repeated calculations:

```python
from functools import lru_cache
from aiogram_cmds import ProfileResolver, Flags

@lru_cache(maxsize=1000)
def cached_profile_resolver(user_id: int, is_registered: bool, has_vehicle: bool) -> str:
    """Cached profile resolver."""
    if has_vehicle:
        return "premium"
    elif is_registered:
        return "user"
    return "guest"

def my_profile_resolver(flags: Flags) -> str:
    user_id = getattr(flags, 'user_id', None)
    if not user_id:
        return "guest"
    
    return cached_profile_resolver(
        user_id, 
        flags.is_registered, 
        flags.has_vehicle
    )
```

### 2. Batch Command Updates

Update multiple users at once to reduce API calls:

```python
async def batch_update_commands(user_updates: list):
    """Update commands for multiple users efficiently."""
    tasks = []
    
    for user_id, flags in user_updates:
        task = manager.update_user_commands(
            user_id=user_id,
            is_registered=flags.get("is_registered", False),
            has_vehicle=flags.get("has_vehicle", False),
            user_language=flags.get("language", "en")
        )
        tasks.append(task)
    
    # Execute all updates concurrently
    await asyncio.gather(*tasks, return_exceptions=True)
```

### 3. Lazy Loading

Load configurations and data only when needed:

```python
class LazyConfig:
    def __init__(self):
        self._config = None
        self._loaded = False
    
    @property
    def config(self):
        if not self._loaded:
            self._config = self._load_config()
            self._loaded = True
        return self._config
    
    def _load_config(self):
        # Load configuration from file or database
        return CmdsConfig(...)

# Usage
lazy_config = LazyConfig()
manager = CommandScopeManager(bot, config=lazy_config.config)
```

### 4. Connection Pooling

Use connection pooling for database operations:

```python
import asyncpg
from aiogram_cmds import ProfileResolver, Flags

class DatabaseProfileResolver:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._cache = {}
    
    async def __call__(self, flags: Flags) -> str:
        user_id = getattr(flags, 'user_id', None)
        if not user_id:
            return "guest"
        
        # Check cache first
        if user_id in self._cache:
            cached_data, timestamp = self._cache[user_id]
            if time.time() - timestamp < 300:  # 5 minutes
                return self._determine_profile(cached_data)
        
        # Query database
        async with self.pool.acquire() as conn:
            user_data = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1", user_id
            )
        
        # Cache result
        self._cache[user_id] = (user_data, time.time())
        
        return self._determine_profile(user_data)
    
    def _determine_profile(self, user_data):
        if user_data.get("banned", False):
            return "banned"
        elif user_data.get("admin", False):
            return "admin"
        elif user_data.get("premium", False):
            return "premium"
        elif user_data.get("registered", False):
            return "user"
        return "guest"
```

### 5. Redis Caching

Redis caching is an application integration, not a built-in backend. The
`redis` extra installs only the client. `ProfileResolver` is synchronous; do not
pass an async function to it. Perform asynchronous lookups before applying an
application-selected profile:

```python
async def update_from_cache(manager, client, user_id: int) -> None:
    cached = await client.get(f"user_profile:{user_id}")
    profile = cached.decode() if cached else "guest"
    await manager.update_profile(user_id, profile)
```

Applications own cache invalidation, authorization, distributed coordination and
recovery. Cached command menus do not enforce handler authorization.

## 📈 Benchmarking

### Command Building Performance

```python
import time
import asyncio
from aiogram_cmds import build_bot_commands

async def benchmark_command_building():
    """Benchmark command building performance."""
    command_names = ["start", "help", "profile", "settings", "admin"]
    translator = my_translator
    
    # Warm up
    for _ in range(10):
        build_bot_commands(command_names, lang="en", translator=translator)
    
    # Benchmark
    start_time = time.time()
    iterations = 1000
    
    for _ in range(iterations):
        build_bot_commands(command_names, lang="en", translator=translator)
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"Command building benchmark:")
    print(f"  Iterations: {iterations}")
    print(f"  Duration: {duration:.3f}s")
    print(f"  Average: {duration/iterations*1000:.3f}ms per build")
    print(f"  Throughput: {iterations/duration:.0f} builds/second")

# Run benchmark
asyncio.run(benchmark_command_building())
```

### Profile Resolution Performance

```python
async def benchmark_profile_resolution():
    """Benchmark profile resolution performance."""
    resolver = my_profile_resolver
    
    # Test cases
    test_flags = [
        Flags(is_registered=False, has_vehicle=False),
        Flags(is_registered=True, has_vehicle=False),
        Flags(is_registered=True, has_vehicle=True),
    ]
    
    # Warm up
    for _ in range(100):
        for flags in test_flags:
            resolver(flags)
    
    # Benchmark
    start_time = time.time()
    iterations = 10000
    
    for _ in range(iterations):
        for flags in test_flags:
            resolver(flags)
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"Profile resolution benchmark:")
    print(f"  Iterations: {iterations}")
    print(f"  Duration: {duration:.3f}s")
    print(f"  Average: {duration/iterations*1000:.3f}ms per resolution")
    print(f"  Throughput: {iterations/duration:.0f} resolutions/second")
```

### Memory Usage

```python
import psutil
import gc
from aiogram_cmds import CommandScopeManager, CmdsConfig

def benchmark_memory_usage():
    """Benchmark memory usage."""
    process = psutil.Process()
    
    # Initial memory
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # Create managers
    managers = []
    for i in range(100):
        config = CmdsConfig(
            languages=["en", "ru", "es"],
            commands={
                f"cmd_{j}": CommandDef(i18n_key=f"cmd_{j}.desc")
                for j in range(10)
            },
            profiles={
                "user": ProfileDef(include=[f"cmd_{j}" for j in range(10)]),
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="user"),
            ],
        )
        manager = CommandScopeManager(bot, config=config)
        managers.append(manager)
    
    # Memory after creation
    creation_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # Clean up
    del managers
    gc.collect()
    
    # Memory after cleanup
    cleanup_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    print(f"Memory usage benchmark:")
    print(f"  Initial: {initial_memory:.1f} MB")
    print(f"  After creation: {creation_memory:.1f} MB")
    print(f"  After cleanup: {cleanup_memory:.1f} MB")
    print(f"  Peak usage: {creation_memory - initial_memory:.1f} MB")
```

## 🔧 Performance Monitoring

### Metrics Collection

```python
import time
from collections import defaultdict
from aiogram_cmds import CommandScopeManager

class PerformanceMonitor:
    def __init__(self):
        self.metrics = defaultdict(list)
        self.start_times = {}
    
    def start_timer(self, operation: str):
        """Start timing an operation."""
        self.start_times[operation] = time.time()
    
    def end_timer(self, operation: str):
        """End timing an operation."""
        if operation in self.start_times:
            duration = time.time() - self.start_times[operation]
            self.metrics[operation].append(duration)
            del self.start_times[operation]
    
    def get_stats(self, operation: str):
        """Get statistics for an operation."""
        if operation not in self.metrics:
            return None
        
        values = self.metrics[operation]
        return {
            "count": len(values),
            "total": sum(values),
            "average": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }
    
    def print_stats(self):
        """Print all statistics."""
        for operation, stats in self.metrics.items():
            if stats:
                avg = sum(stats) / len(stats)
                print(f"{operation}: {len(stats)} calls, avg {avg*1000:.3f}ms")

# Usage
monitor = PerformanceMonitor()

class MonitoredCommandScopeManager(CommandScopeManager):
    async def update_user_commands(self, user_id: int, **flags):
        monitor.start_timer("update_user_commands")
        try:
            result = await super().update_user_commands(user_id, **flags)
            return result
        finally:
            monitor.end_timer("update_user_commands")
```

### Logging Performance

```python
import logging
import time
from functools import wraps

def log_performance(func):
    """Decorator to log function performance."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            logger.info(f"{func.__name__} took {duration*1000:.3f}ms")
    return wrapper

# Usage
@log_performance
async def update_user_commands(user_id: int, **flags):
    await manager.update_user_commands(user_id, **flags)
```

## 🚀 Production Optimizations

### 1. Application-owned Redis integration

This illustrative wrapper is application code. It does not provide distributed
coordination, recovery or an aiogram-cmds storage backend.

```python
import redis.asyncio as redis
from aiogram_cmds import CommandScopeManager

# Redis connection
redis_client = redis.from_url("redis://localhost:6379")

# Use Redis for shared state
class RedisCommandManager:
    def __init__(self, bot, redis_client):
        self.bot = bot
        self.redis = redis_client
        self.manager = CommandScopeManager(bot)
    
    async def update_user_commands(self, user_id: int, **flags):
        # Update Redis cache
        await self.redis.hset(
            f"user_commands:{user_id}",
            mapping=flags
        )
        
        # Update commands
        await self.manager.update_user_commands(user_id, **flags)
```

### 2. Implement Circuit Breaker

```python
import asyncio
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e
    
    def on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED
    
    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

# Usage
circuit_breaker = CircuitBreaker()

async def safe_update_commands(user_id: int, **flags):
    return await circuit_breaker.call(
        manager.update_user_commands,
        user_id,
        **flags
    )
```

### 3. Implement Retry Logic

```python
import asyncio
from functools import wraps

def retry(max_attempts=3, delay=1, backoff=2):
    """Retry decorator with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff ** attempt)
                        await asyncio.sleep(wait_time)
            
            raise last_exception
        return wrapper
    return decorator

# Usage
@retry(max_attempts=3, delay=1, backoff=2)
async def update_user_commands(user_id: int, **flags):
    await manager.update_user_commands(user_id, **flags)
```

## 📊 Performance Metrics

### Key Metrics to Monitor

1. **Command Building Time**
   - Average time to build command list
   - Peak building time
   - Throughput (commands/second)

2. **Profile Resolution Time**
   - Average resolution time
   - Cache hit rate
   - Database query time

3. **API Call Performance**
   - Telegram API response time
   - Rate limit hits
   - Error rates

4. **Memory Usage**
   - Peak memory usage
   - Memory leaks
   - Garbage collection frequency

5. **Concurrent Operations**
   - Number of concurrent updates
   - Queue depth
   - Timeout rates

### Monitoring Dashboard

```python
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class PerformanceMetrics:
    timestamp: float
    operation: str
    duration: float
    success: bool
    error: str = None

class PerformanceDashboard:
    def __init__(self):
        self.metrics: List[PerformanceMetrics] = []
        self.max_metrics = 10000  # Keep last 10k metrics
    
    def record_metric(self, operation: str, duration: float, success: bool, error: str = None):
        """Record a performance metric."""
        metric = PerformanceMetrics(
            timestamp=time.time(),
            operation=operation,
            duration=duration,
            success=success,
            error=error
        )
        
        self.metrics.append(metric)
        
        # Keep only recent metrics
        if len(self.metrics) > self.max_metrics:
            self.metrics = self.metrics[-self.max_metrics:]
    
    def get_stats(self, operation: str, window_minutes: int = 60) -> Dict:
        """Get statistics for an operation in the last N minutes."""
        cutoff_time = time.time() - (window_minutes * 60)
        recent_metrics = [
            m for m in self.metrics
            if m.operation == operation and m.timestamp > cutoff_time
        ]
        
        if not recent_metrics:
            return {"count": 0}
        
        durations = [m.duration for m in recent_metrics]
        successes = [m.success for m in recent_metrics]
        
        return {
            "count": len(recent_metrics),
            "success_rate": sum(successes) / len(successes),
            "avg_duration": sum(durations) / len(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "error_count": len([m for m in recent_metrics if not m.success]),
        }
    
    def print_dashboard(self):
        """Print performance dashboard."""
        print("=== Performance Dashboard ===")
        
        operations = set(m.operation for m in self.metrics)
        for operation in operations:
            stats = self.get_stats(operation)
            if stats["count"] > 0:
                print(f"{operation}:")
                print(f"  Count: {stats['count']}")
                print(f"  Success Rate: {stats['success_rate']:.1%}")
                print(f"  Avg Duration: {stats['avg_duration']*1000:.3f}ms")
                print(f"  Min/Max: {stats['min_duration']*1000:.3f}ms / {stats['max_duration']*1000:.3f}ms")
                print(f"  Errors: {stats['error_count']}")
                print()

# Usage
dashboard = PerformanceDashboard()

# Record metrics
dashboard.record_metric("update_user_commands", 0.1, True)
dashboard.record_metric("update_user_commands", 0.2, False, "Rate limit")

# Print dashboard
dashboard.print_dashboard()
```

## 🎯 Best Practices

### 1. Profile Resolution
- Cache profile resolutions
- Use efficient data structures
- Minimize database queries
- Implement proper cache invalidation

### 2. Command Updates
- Batch updates when possible
- Use async/await properly
- Implement retry logic
- Monitor rate limits

### 3. Memory Management
- Use lazy loading
- Clean up unused objects
- Monitor memory usage
- Implement proper garbage collection

### 4. Error Handling
- Implement circuit breakers
- Use exponential backoff
- Log performance metrics
- Monitor error rates

### 5. Monitoring
- Track key performance metrics
- Set up alerts for anomalies
- Monitor resource usage
- Regular performance reviews

---

**Need help optimizing?** Check out our [Troubleshooting Guide](troubleshooting.md) or [create an issue](https://github.com/ArmanAvanesyan/aiogram-cmds/issues) with performance questions!
