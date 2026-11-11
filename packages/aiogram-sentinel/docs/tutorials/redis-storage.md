# Tutorial: Using Redis Storage

**Goal**: Set up aiogram-sentinel with Redis storage for production use.

**What you'll build**: A bot that uses Redis for persistent storage across restarts.

## Prerequisites

- Python 3.10+
- Redis server running
- aiogram v3 and aiogram-sentinel installed
- Basic understanding of Redis

## Step 1: Install Redis

### On Ubuntu/Debian:
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### On macOS:
```bash
brew install redis
brew services start redis
```

### On Windows:
Download Redis from [redis.io](https://redis.io/download) or use Docker:
```bash
docker run -d -p 6379:6379 redis:alpine
```

## Step 2: Verify Redis Installation

Test Redis connection:

```bash
redis-cli ping
```

You should see `PONG` response.

## Step 3: Install Redis Python Client

```bash
pip install aiogram-sentinel[redis]
```

Or install redis separately:

```bash
pip install redis
```

## Step 4: Basic Redis Configuration

Create `bot.py` with Redis storage:

```python
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram_sentinel import Sentinel, SentinelConfig, rate_limit, debounce

# Initialize bot and dispatcher
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# Configure aiogram-sentinel with Redis
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_prefix="mybot:",
    throttling_default_max=10,
    throttling_default_per_seconds=60,
    debounce_default_window=2,
)

# Setup with one call
router, infra = await Sentinel.setup(dp, config)

@router.message()
@rate_limit(5, 60)
@debounce(1.0)
async def handle_message(message: Message):
    """Handle all messages with protection."""
    await message.answer(f"Hello! Your message: {message.text}")

async def main():
    """Start the bot."""
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Step 5: Redis Connection Options

### Basic Connection
```python
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
)
```

### With Authentication
```python
config = SentinelConfig(
    backend="redis",
    redis_url="redis://username:password@localhost:6379",
)
```

### With Database Selection
```python
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379/1",  # Use database 1
)
```

### With SSL/TLS
```python
config = SentinelConfig(
    backend="redis",
    redis_url="rediss://localhost:6380",  # SSL connection
)
```

## Step 6: Key Prefixing

Use prefixes to avoid key conflicts:

```python
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_prefix="mybot:prod:",  # All keys will start with this
)
```

This creates keys like:
- `mybot:prod:rate:12345:handler_name`
- `mybot:prod:debounce:12345:handler_name:hash`

## Step 7: Connection Pooling

For high-traffic bots, configure connection pooling:

```python
import redis.asyncio as redis

# Create custom Redis connection
redis_client = redis.ConnectionPool.from_url(
    "redis://localhost:6379",
    max_connections=20,
    retry_on_timeout=True,
)

# Use with aiogram-sentinel
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_prefix="mybot:",
)
```

## Step 8: Monitoring Redis Usage

### Check Key Count
```bash
redis-cli dbsize
```

### List Keys
```bash
redis-cli keys "mybot:*"
```

### Monitor Commands
```bash
redis-cli monitor
```

### Check Memory Usage
```bash
redis-cli info memory
```

## Step 9: Production Configuration

For production, use these settings:

```python
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_prefix="mybot:prod:",
    throttling_default_max=20,
    throttling_default_per_seconds=60,
    debounce_default_window=1,
)
```

### Environment Variables
```python
import os

config = SentinelConfig(
    backend="redis",
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
    redis_prefix=os.getenv("REDIS_PREFIX", "mybot:"),
    throttling_default_max=int(os.getenv("RATE_LIMIT", "20")),
    throttling_default_per_seconds=int(os.getenv("RATE_WINDOW", "60")),
    debounce_default_window=int(os.getenv("DEBOUNCE_WINDOW", "1")),
)
```

## Step 10: Error Handling

Add proper error handling for Redis connection issues:

```python
import logging
from redis.exceptions import ConnectionError, TimeoutError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def on_rate_limited(event, data, retry_after):
    """Handle rate limiting with Redis error handling."""
    try:
        await event.answer(f"⏰ Rate limited! Try again in {int(retry_after)} seconds.")
    except (ConnectionError, TimeoutError) as e:
        logger.error(f"Redis connection error: {e}")
        # Fallback behavior
        await event.answer("Service temporarily unavailable. Please try again later.")

# Add the hook
Sentinel.add_hooks(router, infra, config, on_rate_limited=on_rate_limited)
```

## Step 11: Redis Cluster Support

For high availability, use Redis Cluster:

```python
config = SentinelConfig(
    backend="redis",
    redis_url="redis://node1:6379,node2:6379,node3:6379",
    redis_prefix="mybot:",
)
```

## Step 12: Performance Optimization

### Connection Pooling
```python
import redis.asyncio as redis

# Configure connection pool
pool = redis.ConnectionPool.from_url(
    "redis://localhost:6379",
    max_connections=50,
    retry_on_timeout=True,
    socket_keepalive=True,
    socket_keepalive_options={},
)
```

### Pipeline Operations
Redis backends automatically use pipelining for better performance.

### Memory Optimization
```bash
# Set maxmemory policy
redis-cli config set maxmemory-policy allkeys-lru

# Set maxmemory limit
redis-cli config set maxmemory 100mb
```

## Step 13: Backup and Recovery

### Backup Redis Data
```bash
# Create backup
redis-cli bgsave

# Copy RDB file
cp /var/lib/redis/dump.rdb /backup/redis-backup-$(date +%Y%m%d).rdb
```

### Restore from Backup
```bash
# Stop Redis
sudo systemctl stop redis-server

# Copy backup file
cp /backup/redis-backup-20231201.rdb /var/lib/redis/dump.rdb

# Start Redis
sudo systemctl start redis-server
```

## Step 14: Complete Production Example

Here's a complete production-ready example:

```python
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram_sentinel import Sentinel, SentinelConfig, rate_limit, debounce

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# Production configuration
config = SentinelConfig(
    backend="redis",
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
    redis_prefix=os.getenv("REDIS_PREFIX", "mybot:prod:"),
    throttling_default_max=int(os.getenv("RATE_LIMIT", "20")),
    throttling_default_per_seconds=int(os.getenv("RATE_WINDOW", "60")),
    debounce_default_window=int(os.getenv("DEBOUNCE_WINDOW", "1")),
)

# Setup with one call
router, infra = await Sentinel.setup(dp, config)

# Rate limiting hook with error handling
async def on_rate_limited(event, data, retry_after):
    try:
        logger.info(f"Rate limited user {event.from_user.id} for {retry_after}s")
        await event.answer(f"⏰ Rate limited! Try again in {int(retry_after)} seconds.")
    except Exception as e:
        logger.error(f"Error in rate limit hook: {e}")

# Add hooks
Sentinel.add_hooks(router, infra, config, on_rate_limited=on_rate_limited)

@router.message()
@rate_limit(10, 60)
@debounce(1.0)
async def handle_message(message: Message):
    """Handle all messages with protection."""
    try:
        await message.answer(f"Hello! Your message: {message.text}")
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await message.answer("Sorry, something went wrong!")

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

## Troubleshooting

### Common Issues

**Connection refused**: Check if Redis is running and accessible.

**Authentication failed**: Verify Redis password and username.

**Memory issues**: Monitor Redis memory usage and set appropriate limits.

**Performance issues**: Use connection pooling and monitor Redis performance.

### Redis Commands for Debugging

```bash
# Check Redis status
redis-cli ping

# Monitor commands in real-time
redis-cli monitor

# Check memory usage
redis-cli info memory

# List all keys
redis-cli keys "*"

# Check specific keys
redis-cli keys "mybot:*"

# Get key TTL
redis-cli ttl "mybot:rate:12345:handler"

# Delete all keys (careful!)
redis-cli flushdb
```

## Next Steps

1. **Monitor performance**: Use Redis monitoring tools
2. **Set up alerts**: Monitor Redis memory and connection issues
3. **Backup regularly**: Implement automated backup procedures
4. **Scale horizontally**: Use Redis Cluster for high availability
5. **Optimize settings**: Tune Redis configuration for your workload