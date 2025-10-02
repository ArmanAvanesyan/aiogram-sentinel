# Quickstart Guide

Get up and running with aiogram-sentinel in 5 minutes.

## Prerequisites

- Python 3.10 or higher
- Basic knowledge of aiogram v3
- A Telegram bot token

## Installation

Install aiogram-sentinel using pip:

```bash
pip install aiogram-sentinel
```

Or using uv (recommended):

```bash
uv add aiogram-sentinel
```

For Redis storage support:

```bash
pip install aiogram-sentinel[redis]
```

## Minimal Example

Here's a complete bot with basic protection:

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

## What This Does

The minimal example above provides:

- **Rate limiting**: Prevents spam by limiting message frequency
- **Debouncing**: Prevents duplicate message processing
- **Configurable protection**: Customizable limits and windows
- **Easy setup**: One call to configure all middleware

## Configuration

Customize protection settings:

```python
from aiogram_sentinel import Sentinel, SentinelConfig

# Create custom configuration
config = SentinelConfig(
    throttling_default_max=5,      # 5 messages
    throttling_default_per_seconds=60,  # per minute
    debounce_default_window=2,     # 2 second debounce
)

# Setup with custom config
router, infra = await Sentinel.setup(dp, config)
```

## Storage Backends

Choose your storage backend:

```python
from aiogram_sentinel import Sentinel, SentinelConfig

# Memory storage (default, good for development)
config = SentinelConfig(backend="memory")
router, infra = await Sentinel.setup(dp, config)

# Redis storage (recommended for production)
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_prefix="mybot:"
)
router, infra = await Sentinel.setup(dp, config)
```

## Next Steps

1. **Learn more**: Read the [Architecture Guide](ARCHITECTURE.md)
2. **Explore examples**: Check out [examples/](../examples/)
3. **Configure protection**: See [Configuration Guide](configuration.md)
4. **Build tutorials**: Follow [Tutorials](tutorials/)

## Troubleshooting

### Common Issues

**Bot not responding**: Check your bot token and network connection.

**Rate limiting too strict**: Adjust `throttling_default_max` in your configuration.

**Redis connection errors**: Ensure Redis is running and accessible.

### Getting Help

- Check the [Troubleshooting Guide](troubleshooting.md) for detailed solutions
- Look at the [FAQ](faq.md) for common questions
- Open an issue on [GitHub](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)

## What's Next?

Now that you have a basic bot running, explore:

- [Tutorials](tutorials/) - Step-by-step guides for common tasks
- [API Reference](api/) - Complete API documentation
- [Configuration](configuration.md) - Advanced configuration options
- [Examples](../examples/) - Real-world usage examples
