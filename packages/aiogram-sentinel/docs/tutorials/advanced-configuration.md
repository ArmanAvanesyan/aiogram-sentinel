# Tutorial: Advanced Configuration

**Goal**: Master advanced configuration options for aiogram-sentinel.

**What you'll build**: A bot with custom middleware, storage backends, and advanced protection settings.

## Prerequisites

- Completed [Basic Protection Tutorial](basic-protection.md)
- Understanding of aiogram middleware
- Basic knowledge of configuration patterns

## Step 1: Custom Configuration Class

Create a custom configuration class:

```python
from aiogram_sentinel import SentinelConfig
from typing import Callable, Any

class MyBotConfig(SentinelConfig):
    """Custom configuration for my bot."""
    
    def __init__(self):
        super().__init__(
            # Rate limiting settings
            throttling_default_max=10,
            throttling_default_per_seconds=60,
            
            # Debounce settings
            debounce_default_window=3,
            
            # Backend settings
            backend="redis",
            redis_url="redis://localhost:6379",
            redis_prefix="mybot:",
        )
    
    def get_rate_limit_for_handler(self, handler_name: str) -> tuple[int, int]:
        """Custom rate limiting per handler."""
        limits = {
            "start": (5, 60),      # 5 messages per minute
            "help": (3, 60),       # 3 messages per minute
            "admin": (20, 60),     # 20 messages per minute
        }
        return limits.get(handler_name, (self.throttling_default_max, self.throttling_default_per_seconds))
```

## Step 2: Environment-Based Configuration

Use environment variables for different environments:

```python
import os
from aiogram_sentinel import SentinelConfig

def create_config() -> SentinelConfig:
    """Create configuration based on environment."""
    env = os.getenv("ENVIRONMENT", "development")
    
    if env == "production":
        return SentinelConfig(
            backend="redis",
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            redis_prefix=os.getenv("REDIS_PREFIX", "mybot:prod:"),
            throttling_default_max=int(os.getenv("RATE_LIMIT", "20")),
            throttling_default_per_seconds=int(os.getenv("RATE_WINDOW", "60")),
            debounce_default_window=int(os.getenv("DEBOUNCE_WINDOW", "1")),
        )
    else:
        return SentinelConfig(
            backend="memory",
            throttling_default_max=5,
            throttling_default_per_seconds=30,
            debounce_default_window=2,
        )

# Use the configuration
config = create_config()
```

## Step 3: Custom Storage Backend

Create a custom storage backend:

```python
from aiogram_sentinel.storage.base import RateLimiterBackend, DebounceBackend
from typing import Dict, Any
import time
import asyncio

class CustomRateLimiter(RateLimiterBackend):
    """Custom rate limiter using in-memory storage."""
    
    def __init__(self):
        self._counters: Dict[str, list] = {}
        self._lock = asyncio.Lock()
    
    async def allow(self, key: str, limit: int, window: int) -> bool:
        """Check if request is allowed."""
        async with self._lock:
            now = time.time()
            
            # Get or create counter for this key
            if key not in self._counters:
                self._counters[key] = []
            
            # Remove expired entries
            self._counters[key] = [
                timestamp for timestamp in self._counters[key]
                if now - timestamp < window
            ]
            
            # Check if under limit
            if len(self._counters[key]) < limit:
                self._counters[key].append(now)
                return True
            
            return False

class CustomDebounce(DebounceBackend):
    """Custom debounce using in-memory storage."""
    
    def __init__(self):
        self._seen: Dict[str, float] = {}
        self._lock = asyncio.Lock()
    
    async def seen(self, key: str, window: float, fingerprint: str) -> bool:
        """Check if key was seen recently."""
        async with self._lock:
            now = time.time()
            full_key = f"{key}:{fingerprint}"
            
            if full_key in self._seen:
                if now - self._seen[full_key] < window:
                    return True
            
            self._seen[full_key] = now
            return False
```

## Step 4: Using Custom Backends

Use your custom backends with aiogram-sentinel:

```python
from aiogram_sentinel import Sentinel, SentinelConfig
from aiogram_sentinel.types import InfraBundle

# Create custom backends
custom_rate_limiter = CustomRateLimiter()
custom_debounce = CustomDebounce()

# Create infrastructure bundle
infra = InfraBundle(
    rate_limiter=custom_rate_limiter,
    debounce=custom_debounce,
)

# Use with Sentinel
config = SentinelConfig()
router, _ = await Sentinel.setup(dp, config, infra=infra)
```

## Step 5: Advanced Decorator Usage

Use decorators with custom scopes and conditions:

```python
from aiogram_sentinel import rate_limit, debounce
from aiogram.types import Message

# Different scopes for different functionality
@router.message()
@rate_limit(5, 60, scope="commands")
@debounce(1.0, scope="commands")
async def command_handler(message: Message):
    """Commands share the same rate limit."""
    await message.answer("Command executed!")

@router.message()
@rate_limit(10, 60, scope="chat")
@debounce(0.5, scope="chat")
async def chat_handler(message: Message):
    """Chat messages have different limits."""
    await message.answer("Chat message processed!")

# Conditional rate limiting
def is_admin(message: Message) -> bool:
    """Check if user is admin."""
    return message.from_user.id in [123456789, 987654321]

@router.message()
@rate_limit(20, 60)  # Higher limit for admins
@debounce(0.1)       # Lower debounce for admins
async def admin_handler(message: Message):
    """Admin-only handler with higher limits."""
    if not is_admin(message):
        await message.answer("Access denied!")
        return
    
    await message.answer("Admin command executed!")
```

## Step 6: Custom Hooks

Create custom hooks for monitoring and feedback:

```python
import logging
from typing import Dict, Any
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)

async def on_rate_limited(event: TelegramObject, data: Dict[str, Any], retry_after: float):
    """Custom rate limiting hook."""
    user_id = getattr(event, 'from_user', {}).id if hasattr(event, 'from_user') else 'unknown'
    handler_name = data.get('handler', 'unknown')
    
    logger.warning(f"Rate limited: user={user_id}, handler={handler_name}, retry_after={retry_after}")
    
    # Send custom message
    if hasattr(event, 'answer'):
        await event.answer(f"🚫 Rate limited! Try again in {int(retry_after)} seconds.")

# Add the hook
Sentinel.add_hooks(router, infra, config, on_rate_limited=on_rate_limited)
```

## Step 7: Dynamic Configuration

Update configuration at runtime:

```python
class DynamicConfig(SentinelConfig):
    """Configuration that can be updated at runtime."""
    
    def __init__(self):
        super().__init__()
        self._rate_limits: Dict[str, tuple] = {}
    
    def set_rate_limit(self, handler_name: str, limit: int, window: int):
        """Set rate limit for specific handler."""
        self._rate_limits[handler_name] = (limit, window)
    
    def get_rate_limit(self, handler_name: str) -> tuple[int, int]:
        """Get rate limit for handler."""
        return self._rate_limits.get(handler_name, (self.throttling_default_max, self.throttling_default_per_seconds))

# Use dynamic configuration
config = DynamicConfig()
config.set_rate_limit("start", 3, 60)
config.set_rate_limit("help", 5, 60)
```

## Step 8: Middleware Ordering

Control middleware order manually:

```python
from aiogram_sentinel.middlewares import ThrottlingMiddleware, DebounceMiddleware
from aiogram_sentinel.storage.factory import build_infra

# Build infrastructure
infra = build_infra(config)

# Create middlewares
throttling_mw = ThrottlingMiddleware(infra.rate_limiter, config)
debounce_mw = DebounceMiddleware(infra.debounce, config)

# Register in specific order
router.message.middleware(debounce_mw)
router.message.middleware(throttling_mw)

# Or register with custom order
router.message.middleware(debounce_mw, index=0)
router.message.middleware(throttling_mw, index=1)
```

## Step 9: Performance Monitoring

Add performance monitoring:

```python
import time
import asyncio
from functools import wraps

def monitor_performance(func):
    """Decorator to monitor function performance."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"{func.__name__} executed in {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
            raise
    return wrapper

# Apply to handlers
@router.message()
@rate_limit(5, 60)
@debounce(1.0)
@monitor_performance
async def monitored_handler(message: Message):
    """Handler with performance monitoring."""
    await message.answer("Hello!")
```

## Step 10: Complete Advanced Example

Here's a complete advanced configuration example:

```python
import asyncio
import logging
import os
from typing import Dict, Any
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram_sentinel import Sentinel, SentinelConfig, rate_limit, debounce
from aiogram_sentinel.types import InfraBundle

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AdvancedConfig(SentinelConfig):
    """Advanced configuration with custom settings."""
    
    def __init__(self):
        super().__init__(
            backend=os.getenv("BACKEND", "memory"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            redis_prefix=os.getenv("REDIS_PREFIX", "mybot:advanced:"),
            throttling_default_max=int(os.getenv("RATE_LIMIT", "10")),
            throttling_default_per_seconds=int(os.getenv("RATE_WINDOW", "60")),
            debounce_default_window=int(os.getenv("DEBOUNCE_WINDOW", "2")),
        )
        self._custom_limits: Dict[str, tuple] = {}
    
    def set_custom_limit(self, handler: str, limit: int, window: int):
        """Set custom rate limit for handler."""
        self._custom_limits[handler] = (limit, window)
    
    def get_custom_limit(self, handler: str) -> tuple[int, int] | None:
        """Get custom rate limit for handler."""
        return self._custom_limits.get(handler)

# Initialize bot and dispatcher
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# Create advanced configuration
config = AdvancedConfig()
config.set_custom_limit("start", 3, 60)
config.set_custom_limit("help", 5, 60)
config.set_custom_limit("admin", 20, 60)

# Setup with one call
router, infra = await Sentinel.setup(dp, config)

# Advanced rate limiting hook
async def on_rate_limited(event: Message, data: Dict[str, Any], retry_after: float):
    """Advanced rate limiting hook with custom logic."""
    user_id = event.from_user.id
    handler_name = data.get('handler', 'unknown')
    
    # Log with context
    logger.warning(f"Rate limited: user={user_id}, handler={handler_name}, retry_after={retry_after}")
    
    # Custom message based on handler
    if handler_name == "start":
        await event.answer("🚫 Too many start commands! Try again later.")
    elif handler_name == "help":
        await event.answer("🚫 Too many help requests! Try again later.")
    else:
        await event.answer(f"🚫 Rate limited! Try again in {int(retry_after)} seconds.")

# Add hooks
Sentinel.add_hooks(router, infra, config, on_rate_limited=on_rate_limited)

# Handlers with different protection levels
@router.message()
@rate_limit(3, 60, scope="start")
@debounce(2.0, scope="start")
async def start_handler(message: Message):
    """Start command with strict protection."""
    await message.answer("Welcome! Use /help for commands.")

@router.message()
@rate_limit(5, 60, scope="help")
@debounce(1.0, scope="help")
async def help_handler(message: Message):
    """Help command with moderate protection."""
    await message.answer("Available commands: /start, /help")

@router.message()
@rate_limit(20, 60, scope="admin")
@debounce(0.5, scope="admin")
async def admin_handler(message: Message):
    """Admin command with lenient protection."""
    if message.from_user.id not in [123456789, 987654321]:
        await message.answer("Access denied!")
        return
    
    await message.answer("Admin command executed!")

@router.message()
@rate_limit(10, 60, scope="general")
@debounce(1.0, scope="general")
async def general_handler(message: Message):
    """General message handler."""
    await message.answer(f"Received: {message.text}")

async def main():
    """Start the bot."""
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot startup error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
```

## Next Steps

1. **Experiment with configurations**: Try different rate limits and debounce settings
2. **Monitor performance**: Use logging and monitoring to track effectiveness
3. **Create custom backends**: Implement storage backends for your specific needs
4. **Add more hooks**: Create custom hooks for monitoring and feedback
5. **Test thoroughly**: Verify behavior under different load conditions

## Troubleshooting

### Common Issues

**Configuration not applied**: Check that configuration is passed correctly to setup.

**Custom backends not working**: Ensure backends implement the required protocols.

**Performance issues**: Monitor middleware execution time and optimize accordingly.

### Debugging Tips

1. **Enable debug logging**: Set logging level to DEBUG
2. **Monitor Redis keys**: Use Redis CLI to inspect stored data
3. **Profile middleware**: Measure execution time of each middleware
4. **Test edge cases**: Verify behavior with rapid requests and edge cases