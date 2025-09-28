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
pip install redis
```

## Step 4: Create Redis-Enabled Bot

Create `redis_bot.py`:

```python
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram_sentinel import Sentinel
from aiogram_sentinel.storage import RedisStorage

# Initialize bot and dispatcher
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# Create Redis storage
redis_storage = RedisStorage("redis://localhost:6379")

# Create Sentinel with Redis storage
sentinel = Sentinel(storage=redis_storage)

# Register middleware
dp.message.middleware(sentinel.middleware)

@dp.message()
async def handle_message(message: Message):
    """Handle all messages with Redis-backed protection."""
    await message.answer(f"Hello! Your message: {message.text}")

async def main():
    """Start the bot."""
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Step 5: Test Redis Persistence

1. **Start your bot**:
   ```bash
   python redis_bot.py
   ```

2. **Send some messages** to trigger rate limiting

3. **Stop the bot** (Ctrl+C)

4. **Restart the bot** and send more messages

5. **Verify**: Rate limiting should persist across restarts

## Step 6: Monitor Redis Data

Check what's stored in Redis:

```bash
redis-cli
```

```redis
# List all keys
KEYS *

# Check rate limit data
GET "aiogram_sentinel:rate_limit:user:12345:handler"

# Check blocklist
SISMEMBER "aiogram_sentinel:blocklist" "12345"

# Check debounce data
GET "aiogram_sentinel:debounce:user:12345:handler"
```

## Step 7: Configure Redis Connection

Customize Redis connection settings:

```python
from aiogram_sentinel.storage import RedisStorage

# Custom Redis configuration
redis_storage = RedisStorage(
    url="redis://localhost:6379",
    namespace="my_bot",  # Custom namespace
    key_prefix="protection:",  # Custom key prefix
    db=1,  # Use database 1
    password="your_password",  # If Redis has auth
    socket_timeout=5,
    socket_connect_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30,
)
```

## Step 8: Add Redis Health Check

Add a command to check Redis connection:

```python
@dp.message(Command("redis_status"))
async def redis_status(message: Message):
    """Check Redis connection status."""
    try:
        # Test Redis connection
        await sentinel.rate_limiter_backend.get_rate_limit("test_key")
        await message.answer("✅ Redis connection is healthy")
    except Exception as e:
        await message.answer(f"❌ Redis connection error: {e}")
```

## Step 9: Handle Redis Connection Errors

Add error handling for Redis connection issues:

```python
import logging
from redis.exceptions import ConnectionError, TimeoutError

# Set up logging
logging.basicConfig(level=logging.INFO)

@dp.message()
async def handle_message(message: Message):
    """Handle messages with Redis error handling."""
    try:
        await message.answer(f"Hello! Your message: {message.text}")
    except (ConnectionError, TimeoutError) as e:
        logging.error(f"Redis connection error: {e}")
        await message.answer("Service temporarily unavailable. Please try again later.")
```

## Step 10: Production Configuration

For production, use environment variables:

```python
import os
from aiogram_sentinel.storage import RedisStorage

# Get Redis URL from environment
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

# Create storage with environment configuration
redis_storage = RedisStorage(
    url=redis_url,
    namespace=os.getenv("REDIS_NAMESPACE", "aiogram_sentinel"),
    key_prefix=os.getenv("REDIS_KEY_PREFIX", "protection:"),
    db=int(os.getenv("REDIS_DB", "0")),
    password=os.getenv("REDIS_PASSWORD"),
)
```

## Verify Results

Your Redis-enabled bot should:
- ✅ Persist rate limiting across restarts
- ✅ Maintain blocklist across restarts
- ✅ Store debounce data persistently
- ✅ Handle Redis connection errors gracefully
- ✅ Support multiple bot instances

## What's Next?

- [Advanced Configuration Tutorial](advanced-configuration.md)
- [Custom Middleware Tutorial](custom-middleware.md)
- [Performance Optimization Tutorial](performance-optimization.md)

## Troubleshooting

**Redis connection refused**: Ensure Redis server is running and accessible.

**Authentication errors**: Check Redis password and user permissions.

**Memory issues**: Monitor Redis memory usage and configure eviction policies.

**Performance issues**: Consider Redis clustering for high-load scenarios.
