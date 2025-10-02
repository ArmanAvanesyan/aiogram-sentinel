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
