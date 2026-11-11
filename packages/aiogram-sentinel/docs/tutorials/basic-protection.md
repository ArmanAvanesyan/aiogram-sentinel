# Tutorial: Basic Bot Protection

**Goal**: Build a Telegram bot with rate limiting and debouncing protection.

**What you'll build**: A bot that handles messages with rate limiting and duplicate message prevention.

## Prerequisites

- Python 3.10+
- aiogram v3 installed
- A Telegram bot token
- Basic understanding of async/await

## Step 1: Project Setup

Create a new directory and install dependencies:

```bash
mkdir my-protected-bot
cd my-protected-bot
pip install aiogram aiogram-sentinel
```

## Step 2: Basic Bot Structure

Create `bot.py`:

```python
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram_sentinel import Sentinel, SentinelConfig, rate_limit, debounce

# Initialize bot and dispatcher
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# Configure aiogram-sentinel
config = SentinelConfig(
    throttling_default_max=10,  # 10 messages per window
    throttling_default_per_seconds=60,  # 60 second window
    debounce_default_window=2,  # 2 second debounce
)

# Setup with one call - wires all middleware in recommended order
router, infra = await Sentinel.setup(dp, config)

@router.message()
@rate_limit(5, 60)  # 5 messages per minute
@debounce(1.0)      # 1 second debounce
async def handle_message(message: Message):
    """Handle all messages with protection."""
    await message.answer(f"Hello! Your message: {message.text}")

async def main():
    """Start the bot."""
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Step 3: Understanding the Protection

The bot now has two layers of protection:

### Rate Limiting
- **Global limit**: 10 messages per 60 seconds (from config)
- **Handler limit**: 5 messages per 60 seconds (from decorator)
- **Sliding window**: Uses the most restrictive limit

### Debouncing
- **Global debounce**: 2 seconds (from config)
- **Handler debounce**: 1 second (from decorator)
- **Fingerprinting**: Prevents duplicate messages

## Step 4: Testing the Protection

Run your bot and test the protection:

```bash
python bot.py
```

Try these tests:
1. **Rate limiting**: Send 6 messages quickly - the 6th should be rate limited
2. **Debouncing**: Send the same message twice quickly - the second should be ignored
3. **Normal usage**: Send different messages with normal timing - should work fine

## Step 5: Custom Configuration

Let's customize the protection for different handlers:

```python
@router.message()
@rate_limit(3, 30)  # 3 messages per 30 seconds
@debounce(0.5)      # 0.5 second debounce
async def strict_handler(message: Message):
    """Strict protection for sensitive commands."""
    await message.answer("This is a strictly protected handler!")

@router.message()
@rate_limit(20, 60)  # 20 messages per minute
@debounce(2.0)       # 2 second debounce
async def lenient_handler(message: Message):
    """More lenient protection for general chat."""
    await message.answer("This handler allows more messages!")
```

## Step 6: Adding Hooks

Add custom feedback when rate limiting occurs:

```python
async def on_rate_limited(event, data, retry_after):
    """Called when rate limit is exceeded."""
    await event.answer(f"⏰ Rate limited! Try again in {int(retry_after)} seconds.")

# Add the hook
Sentinel.add_hooks(router, infra, config, on_rate_limited=on_rate_limited)
```

## Step 7: Using Scopes

Use scopes to group related handlers:

```python
@router.message()
@rate_limit(5, 60, scope="commands")
@debounce(1.0, scope="commands")
async def command_handler(message: Message):
    """Commands share the same rate limit."""
    await message.answer("Command executed!")

@router.message()
@rate_limit(5, 60, scope="commands")  # Same scope = shared limit
@debounce(1.0, scope="commands")
async def another_command_handler(message: Message):
    """Another command sharing the same rate limit."""
    await message.answer("Another command executed!")
```

## Step 8: Production Configuration

For production, use Redis backend:

```python
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_prefix="mybot:",
    throttling_default_max=10,
    throttling_default_per_seconds=60,
    debounce_default_window=2,
)
```

## Step 9: Error Handling

Add proper error handling:

```python
@router.message()
@rate_limit(5, 60)
@debounce(1.0)
async def handle_message(message: Message):
    """Handle all messages with protection."""
    try:
        await message.answer(f"Hello! Your message: {message.text}")
    except Exception as e:
        print(f"Error handling message: {e}")
        await message.answer("Sorry, something went wrong!")
```

## Step 10: Monitoring

Add logging to monitor protection effectiveness:

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def on_rate_limited(event, data, retry_after):
    """Log rate limiting events."""
    logger.info(f"Rate limited user {event.from_user.id} for {retry_after}s")
    await event.answer(f"⏰ Rate limited! Try again in {int(retry_after)} seconds.")
```

## Complete Example

Here's the complete `bot.py`:

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram_sentinel import Sentinel, SentinelConfig, rate_limit, debounce

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# Configure aiogram-sentinel
config = SentinelConfig(
    backend="memory",  # Use "redis" for production
    throttling_default_max=10,
    throttling_default_per_seconds=60,
    debounce_default_window=2,
)

# Setup with one call
router, infra = await Sentinel.setup(dp, config)

# Rate limiting hook
async def on_rate_limited(event, data, retry_after):
    logger.info(f"Rate limited user {event.from_user.id} for {retry_after}s")
    await event.answer(f"⏰ Rate limited! Try again in {int(retry_after)} seconds.")

# Add hooks
Sentinel.add_hooks(router, infra, config, on_rate_limited=on_rate_limited)

@router.message()
@rate_limit(5, 60)
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Next Steps

1. **Test thoroughly**: Try different scenarios to understand the protection
2. **Monitor performance**: Use logging to track rate limiting effectiveness
3. **Tune settings**: Adjust limits based on your bot's usage patterns
4. **Add more handlers**: Create different protection levels for different commands
5. **Deploy to production**: Use Redis backend for production deployment

## Troubleshooting

### Common Issues

**Bot not responding**: Check your bot token and network connection.

**Rate limiting too strict**: Adjust `throttling_default_max` in your configuration.

**Redis connection errors**: Ensure Redis is running and accessible.

### Getting Help

- Check the [Troubleshooting Guide](../troubleshooting.md) for detailed solutions
- Look at the [FAQ](../faq.md) for common questions
- Open an issue on [GitHub](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)