# Troubleshooting Guide

Common issues and solutions for aiogram-sentinel.

> **Quick Help**: For common questions, see the [FAQ](faq.md). For step-by-step guides, see the [Tutorials](tutorials/).

## Quick Diagnosis

### Check Bot Status

```python
@dp.message(Command("status"))
async def bot_status(message: Message):
    """Check bot and middleware status."""
    status = {
        "bot_running": True,
        "middleware_registered": hasattr(dp.message, 'middleware'),
        "storage_connected": await check_storage_connection(),
    }
    
    await message.answer(f"Bot Status: {status}")
```

### Enable Debug Logging

```python
import logging

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Policy Registry Issues

### Policy Not Found Errors

**Symptoms**: `ValueError: Policy 'policy_name' not found`

**Solutions**:

1. **Check policy registration**:
```python
from aiogram_sentinel import registry

# List all registered policies
print("Registered policies:", [p.name for p in registry.all()])

# Check if policy exists
try:
    policy = registry.get("your_policy_name")
    print(f"Policy found: {policy}")
except ValueError as e:
    print(f"Policy error: {e}")
```

2. **Verify policy name spelling**:
```python
# The error message includes suggestions
try:
    registry.get("user_throtle")  # Typo
except ValueError as e:
    print(e)  # "Policy 'user_throtle' not found. Did you mean: user_throttle"
```

3. **Register policy before use**:
```python
from aiogram_sentinel import registry, Policy, ThrottleCfg, Scope

# Register policy first
registry.register(Policy(
    "user_throttle", "throttle",
    ThrottleCfg(rate=5, per=60, scope=Scope.USER)
))

# Then use it
@policy("user_throttle")
async def handler(message):
    await message.answer("Hello!")
```

### Policy Skipped Due to Missing Scope Identifiers

**Symptoms**: Policy not applied, debug log shows "Policy skipped: required scope identifiers missing"

**Solutions**:

1. **Check scope cap requirements**:
```python
from aiogram_sentinel import resolve_scope, Scope

# Test scope resolution
user_id = 123
chat_id = 456
cap = Scope.USER

resolved = resolve_scope(user_id, chat_id, cap)
if resolved is None:
    print(f"Cannot satisfy scope cap {cap} with user_id={user_id}, chat_id={chat_id}")
else:
    print(f"Resolved scope: {resolved}")
```

2. **Adjust scope cap or ensure identifiers are available**:
```python
# Option 1: Use more permissive scope cap
registry.register(Policy(
    "flexible_throttle", "throttle",
    ThrottleCfg(rate=5, per=60, scope=Scope.GROUP)  # More permissive than USER
))

# Option 2: Ensure user_id is available in context
# Check your handler context extraction
```

3. **Debug scope resolution**:
```python
import logging

# Enable debug logging to see scope resolution
logging.getLogger("aiogram_sentinel").setLevel(logging.DEBUG)

# You'll see logs like:
# "Policy skipped: required scope identifiers missing" with context
```

### Deprecation Warnings for Old Decorators

**Symptoms**: `DeprecationWarning: @rate_limit is deprecated`

**Solutions**:

1. **Migrate to policy registry**:
```python
# Before (deprecated)
@rate_limit(5, 60, scope="user")
@debounce(2, scope="chat")
async def handler(message):
    await message.answer("Hello!")

# After (recommended)
from aiogram_sentinel import registry, policy, Policy, ThrottleCfg, DebounceCfg, Scope

# Register policies once
registry.register(Policy("user_throttle", "throttle", ThrottleCfg(rate=5, per=60, scope=Scope.USER)))
registry.register(Policy("chat_debounce", "debounce", DebounceCfg(window=2, scope=Scope.CHAT)))

# Use policies
@policy("user_throttle", "chat_debounce")
async def handler(message):
    await message.answer("Hello!")
```

2. **Suppress warnings temporarily**:
```python
import warnings

# Suppress deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="aiogram_sentinel")
```

### Policy Resolution Conflicts

**Symptoms**: Warning about both @policy and legacy decorators found

**Solutions**:

1. **Remove legacy decorators**:
```python
# Problem: Both policy and legacy decorator
@policy("user_throttle")
@rate_limit(5, 60)  # This will be ignored with warning
async def handler(message):
    await message.answer("Hello!")

# Solution: Remove legacy decorator
@policy("user_throttle")
async def handler(message):
    await message.answer("Hello!")
```

2. **Use only legacy decorators** (temporary):
```python
# If you need to keep legacy decorators temporarily
@rate_limit(5, 60)
async def handler(message):
    await message.answer("Hello!")
# Don't use @policy decorator
```

### Policy Configuration Validation Errors

**Symptoms**: `ValueError: rate must be positive` or similar validation errors

**Solutions**:

1. **Check configuration values**:
```python
from aiogram_sentinel import ThrottleCfg, DebounceCfg

# Valid configurations
throttle_cfg = ThrottleCfg(rate=5, per=60)  # rate > 0, per > 0
debounce_cfg = DebounceCfg(window=2)        # window > 0

# Invalid configurations will raise ValueError
try:
    invalid_cfg = ThrottleCfg(rate=0, per=60)  # rate must be > 0
except ValueError as e:
    print(f"Configuration error: {e}")
```

2. **Validate before registration**:
```python
def safe_register_policy(policy):
    """Safely register policy with validation."""
    try:
        registry.register(policy)
        print(f"Policy '{policy.name}' registered successfully")
    except ValueError as e:
        print(f"Failed to register policy '{policy.name}': {e}")
```

## Key Generation Issues

### Debugging Generated Keys

**Symptoms**: Keys not working as expected, rate limiting not functioning correctly

**Solutions**:

1. **Enable key debugging**:
```python
import logging

# Enable debug logging to see generated keys
logging.getLogger("aiogram_sentinel").setLevel(logging.DEBUG)
```

2. **Print generated keys**:
```python
from aiogram_sentinel import KeyBuilder

kb = KeyBuilder(app="mybot")
key = kb.user("throttle", 12345)
print(f"Generated key: {key}")
# Output: mybot:throttle:USER:12345
```

3. **Verify key format**:
```python
# Check key components
parts = key.split(":")
print(f"App: {parts[0]}")
print(f"Namespace: {parts[1]}")
print(f"Scope: {parts[2]}")
print(f"Identifiers: {parts[3:]}")
```

### Key Validation Errors

**Symptoms**: `ValueError` when creating keys

**Common Causes**:
- Empty namespace or identifiers
- Separator characters in identifiers
- Invalid scope usage

**Solutions**:

1. **Check namespace**:
```python
# ❌ Invalid
parts = KeyParts(namespace="", scope=Scope.USER, identifiers=("123",))

# ✅ Valid
parts = KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123",))
```

2. **Check identifiers**:
```python
# ❌ Invalid - contains separator
parts = KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123:456",))

# ✅ Valid
parts = KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123", "456"))
```

3. **Check scope usage**:
```python
# ❌ Invalid - GROUP scope with single identifier
parts = KeyParts(namespace="throttle", scope=Scope.GROUP, identifiers=("123",))

# ✅ Valid - GROUP scope with two identifiers
parts = KeyParts(namespace="throttle", scope=Scope.GROUP, identifiers=("123", "456"))
```

### Context Extraction Issues

**Symptoms**: Wrong user/chat IDs extracted from events

**Solutions**:

1. **Debug context extraction**:
```python
from aiogram_sentinel.context import extract_user_id, extract_chat_id

user_id = extract_user_id(event, data)
chat_id = extract_chat_id(event, data)

print(f"Extracted user_id: {user_id}")
print(f"Extracted chat_id: {chat_id}")
print(f"Event type: {event.__class__.__name__}")
```

2. **Check event attributes**:
```python
# For Message events
if hasattr(event, 'from_user'):
    print(f"from_user: {event.from_user}")
if hasattr(event, 'chat'):
    print(f"chat: {event.chat}")

# For CallbackQuery events
if hasattr(event, 'data'):
    print(f"callback data: {event.data}")
```

3. **Handle missing context**:
```python
# Check if context is available
user_id, chat_id = extract_group_ids(event, data)

if user_id and chat_id:
    # Use GROUP scope
    key = kb.group("throttle", user_id, chat_id)
elif user_id:
    # Use USER scope
    key = kb.user("throttle", user_id)
elif chat_id:
    # Use CHAT scope
    key = kb.chat("throttle", chat_id)
else:
    # Use GLOBAL scope
    key = kb.global_("throttle")
```

### Deprecation Warnings

**Symptoms**: Deprecation warnings for `rate_key()` and `debounce_key()`

**Solutions**:

1. **Update to KeyBuilder**:
```python
# ❌ Deprecated
from aiogram_sentinel.utils.keys import rate_key, debounce_key

key = rate_key(user_id, handler_name, **kwargs)

# ✅ Recommended
from aiogram_sentinel import KeyBuilder

kb = KeyBuilder(app="sentinel")
key = kb.user("throttle", user_id, bucket=handler_name, **kwargs)
```

2. **Suppress warnings temporarily**:
```python
import warnings

# Suppress deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

### Key Collision Detection

**Symptoms**: Different inputs producing same keys

**Solutions**:

1. **Test key uniqueness**:
```python
keys = set()
for user_id in range(1000):
    key = kb.user("throttle", user_id)
    if key in keys:
        print(f"Key collision detected: {key}")
    keys.add(key)
```

2. **Verify key components**:
```python
# Test different namespaces
key1 = kb.user("throttle", 123)
key2 = kb.user("debounce", 123)
assert key1 != key2, "Keys should be different for different namespaces"

# Test different scopes
key3 = kb.user("throttle", 123)
key4 = kb.chat("throttle", 123)
assert key3 != key4, "Keys should be different for different scopes"
```

### Performance Issues

**Symptoms**: Slow key generation or high memory usage

**Solutions**:

1. **Reuse KeyBuilder instances**:
```python
# ❌ Inefficient - creates new instance each time
def generate_key(user_id):
    kb = KeyBuilder(app="mybot")
    return kb.user("throttle", user_id)

# ✅ Efficient - reuse instance
kb = KeyBuilder(app="mybot")

def generate_key(user_id):
    return kb.user("throttle", user_id)
```

2. **Cache frequently used keys**:
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_user_key(user_id: int) -> str:
    kb = KeyBuilder(app="mybot")
    return kb.user("throttle", user_id)
```

## Common Issues

### Bot Not Responding

**Symptoms**: Bot doesn't respond to messages

**Possible Causes**:
- Bot token invalid or expired
- Middleware not registered
- Network connectivity issues
- Bot blocked by user

**Solutions**:

1. **Check bot token**:
   ```python
   from aiogram import Bot
   
   bot = Bot(token="YOUR_TOKEN")
   print(f"Bot info: {await bot.get_me()}")
   ```

2. **Verify middleware registration**:
   ```python
   # Check if middleware is registered
   print(f"Middleware registered: {hasattr(dp.message, 'middleware')}")
   ```

3. **Test basic functionality**:
   ```python
   @dp.message()
   async def test_handler(message: Message):
       await message.answer("Bot is working!")
   ```

### Rate Limiting Issues

**Symptoms**: Users get blocked unexpectedly or rate limiting doesn't work

**Possible Causes**:
- Configuration too strict
- Time zone issues
- Storage backend problems
- Handler-specific overrides

**Solutions**:

1. **Check current configuration**:
   ```python
   @dp.message(Command("config"))
   async def show_config(message: Message):
       config = sentinel.config
       await message.answer(f"Rate limit: {config.throttling_default_max}/{config.throttling_default_per_seconds}s")
   ```

2. **Adjust rate limits**:
   ```python
   # More lenient configuration
   config = SentinelConfig(
       throttling_default_max=20,  # Increase limit
       throttling_default_per_seconds=10,
   )
   ```

3. **Check handler-specific settings**:
   ```python
   # Remove strict decorators
   @dp.message(Command("start"))
   # @sentinel_rate_limit(limit=1, window=60)  # Comment out
   async def start_handler(message: Message):
       await message.answer("Welcome!")
   ```

### Redis Connection Issues

**Symptoms**: Redis connection errors, storage not working

**Possible Causes**:
- Redis server not running
- Wrong connection URL
- Authentication issues
- Network problems

**Solutions**:

1. **Check Redis server**:
   ```bash
   # Test Redis connection
   redis-cli ping
   # Should return: PONG
   ```

2. **Verify connection URL**:
   ```python
   # Test Redis connection
   import redis
   
   try:
       r = redis.from_url("redis://localhost:6379")
       r.ping()
       print("Redis connection successful")
   except Exception as e:
       print(f"Redis connection failed: {e}")
   ```

3. **Check Redis configuration**:
   ```python
   # Use memory storage as fallback
   config = SentinelConfig(backend="memory")  # Fallback to memory
   router, infra = await Sentinel.setup(dp, config)
   ```

### Debouncing Issues

**Symptoms**: Messages are debounced when they shouldn't be, or debouncing doesn't work

**Possible Causes**:
- Debounce window too long
- Key generation issues
- Storage backend problems

**Solutions**:

1. **Check debounce configuration**:
   ```python
   config = SentinelConfig(
       debounce_default_window=1,  # Reduce debounce time
   )
   ```

2. **Test debounce functionality**:
   ```python
   @dp.message(Command("test_debounce"))
   async def test_debounce(message: Message):
       key = f"user:{message.from_user.id}:test"
       
       # Test debounce
       is_seen = await sentinel.debounce_backend.seen(key, 5, "test_fingerprint")
       
       await message.answer(f"Debounce test: {is_seen}")
   ```

3. **Check key generation**:
   ```python
   from aiogram_sentinel.utils.keys import debounce_key
   
   key = debounce_key("user", 12345, "test", "fingerprint")
   print(f"Generated key: {key}")
   ```


## Performance Issues

### High Memory Usage

**Symptoms**: Bot consumes too much memory

**Solutions**:

1. **Use Redis storage**:
   ```python
   # Switch from memory to Redis
   config = SentinelConfig(
       backend="redis",
       redis_url="redis://localhost:6379"
   )
   router, infra = await Sentinel.setup(dp, config)
   ```

2. **Configure cleanup**:
   ```python
   # Enable automatic cleanup
   config = SentinelConfig(
       # Reduce retention time
       throttling_default_per_seconds=10,  # 10 seconds
   )
   ```

3. **Monitor memory usage**:
   ```python
   import psutil
   import os
   
   @dp.message(Command("memory"))
   async def memory_usage(message: Message):
       process = psutil.Process(os.getpid())
       memory_mb = process.memory_info().rss / 1024 / 1024
       await message.answer(f"Memory usage: {memory_mb:.2f} MB")
   ```

### Slow Response Times

**Symptoms**: Bot responds slowly to messages

**Solutions**:

1. **Optimize storage backend**:
   ```python
   # Use faster Redis configuration
   config = SentinelConfig(
       backend="redis",
       redis_url="redis://localhost:6379",
   )
   router, infra = await Sentinel.setup(dp, config)
   ```

2. **Reduce middleware complexity**:
   ```python
   # Use minimal configuration
   config = SentinelConfig(
       throttling_default_max=10,  # Reduce rate limit
       debounce_default_window=1,  # Reduce debounce time
   )
   ```

3. **Monitor performance**:
   ```python
   import time
   
   @dp.message()
   async def timed_handler(message: Message):
       start_time = time.time()
       
       # Your handler logic here
       await message.answer("Response")
       
       end_time = time.time()
       print(f"Handler took {end_time - start_time:.3f} seconds")
   ```

## Error Messages

### ConfigurationError

**Message**: `"throttling_default_max must be positive"`

**Solution**: Ensure all numeric configuration values are positive:
```python
config = SentinelConfig(
    throttling_default_max=5,  # Must be > 0
    throttling_default_per_seconds=60,  # Must be > 0
)
```

### StorageError

**Message**: `"Storage operation failed"`

**Solution**: Check storage backend connection and configuration:
```python
# Test storage connection
try:
    # Test with a simple operation
    await infra.rate_limiter.allow("test", 1, 1)
    print("Storage connection successful")
except Exception as e:
    print(f"Storage error: {e}")
```

### ImportError

**Message**: `"No module named 'aiogram_sentinel'"`

**Solution**: Install aiogram-sentinel:
```bash
pip install aiogram-sentinel
```

## Debugging Tools

### Enable Verbose Logging

```python
import logging

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
```

### Health Check Endpoint

```python
@dp.message(Command("health"))
async def health_check(message: Message):
    """Comprehensive health check."""
    health = {
        "bot": "healthy",
        "middleware": "registered",
        "storage": await check_storage_health(),
        "rate_limiter": await check_rate_limiter_health(),
        "debounce": await check_debounce_health(),
    }
    
    await message.answer(f"Health Status: {health}")

async def check_storage_health():
    try:
        # Test with a simple operation
        await infra.rate_limiter.allow("health_check", 1, 1)
        return "healthy"
    except Exception:
        return "unhealthy"
```

### Performance Monitoring

```python
import time
from functools import wraps

def monitor_performance(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        end_time = time.time()
        
        print(f"{func.__name__} took {end_time - start_time:.3f} seconds")
        return result
    
    return wrapper

@monitor_performance
@dp.message()
async def monitored_handler(message: Message):
    await message.answer("Response")
```

## Getting Help

### Before Asking for Help

1. **Check this troubleshooting guide**
2. **Enable debug logging**
3. **Test with minimal configuration**
4. **Check aiogram-sentinel version**
5. **Verify Python and aiogram versions**

### Provide Information

When reporting issues, include:

- **aiogram-sentinel version**: `pip show aiogram-sentinel`
- **Python version**: `python --version`
- **aiogram version**: `pip show aiogram`
- **Error messages**: Full traceback
- **Configuration**: Your SentinelConfig settings
- **Storage backend**: Memory or Redis
- **Environment**: OS, Python version, etc.

### Community Support

- **GitHub Issues**: [Report bugs and request features](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)
- **Discussions**: [Ask questions and share ideas](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions)
- **Documentation**: [Read the full documentation](https://github.com/ArmanAvanesyan/aiogram-sentinel/tree/main/docs)
