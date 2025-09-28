# aiogram-sentinel

**Drop-in middlewares for aiogram v3 with batteries included** - Protect your Telegram bots from spam, abuse, and unwanted behavior with powerful middleware and storage backends.

## Quick Start

```python
from aiogram import Bot, Dispatcher
from aiogram_sentinel import Sentinel, SentinelConfig

# Create bot and dispatcher
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# Configure aiogram-sentinel
config = SentinelConfig(
    throttling_default_max=10,  # 10 messages per window
    throttling_default_per_seconds=60,  # 60 second window
)

# Setup with one call - wires all middleware in recommended order
sentinel = Sentinel(config=config)
dp.message.middleware(sentinel.middleware)

# Your handlers now have access to user context
@dp.message()
async def handle_message(message, data):
    user_context = data["user_context"]  # Available after auth middleware
    await message.answer(f"Hello {user_context['username']}!")

# Start your bot
await dp.start_polling(bot)
```

## Features

* **Auth bootstrap** with pluggable resolver → expose `data["user_context"]` without locking you to a DB.
* **Blocking:** deny early if user is blocked; auto-sync block/unblock via `my_chat_member`, with `on_block` / `on_unblock` hooks.
* **Debouncing:** suppress duplicate messages/callbacks within a window.
* **Throttling:** per-user/handler scopes; notifier hook for UX.
* **Backends:** memory (single worker) or redis (multi-worker), with configurable `redis_prefix`.
* **Setup helper:** `Sentinel.setup(dp, cfg)` wires recommended order and membership router.
* **Typed, async-first, production-ready.**

## Installation

```bash
# Basic installation
pip install aiogram-sentinel

# With Redis support
pip install aiogram-sentinel[redis]
```

## Documentation

- **[Quickstart](quickstart.md)** - Get started in 5 minutes
- **[Configuration](configuration.md)** - Complete configuration guide
- **[API Reference](api/)** - Full API documentation
- **[Tutorials](tutorials/)** - Step-by-step guides
- **[Performance](performance.md)** - Benchmarks and optimization
- **[Migration Guides](migration-guides/)** - Upgrade instructions
- **[Roadmap](roadmap.md)** - Future plans and features
- **[Examples](../examples/)** - Complete working examples

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and setup instructions.

## Security

For security issues, see [SECURITY.md](SECURITY.md).

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.
