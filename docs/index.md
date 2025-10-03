# aiogram-sentinel

**Rate limiting and debouncing middleware for aiogram v3** - Protect your Telegram bots from spam and abuse with powerful middleware and storage backends.

## Quick Start

```python
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram_sentinel import Sentinel, SentinelConfig, rate_limit, debounce

# Create bot and dispatcher
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

# Your handlers with protection
@router.message()
@rate_limit(5, 60)  # 5 messages per minute
@debounce(1.0)      # 1 second debounce
async def handle_message(message: Message):
    await message.answer(f"Hello! Your message: {message.text}")

# Start your bot
await dp.start_polling(bot)
```

## Features

* **Rate Limiting:** Per-user/handler scopes with sliding window algorithm
* **Debouncing:** Suppress duplicate messages/callbacks within a configurable window
* **Storage Backends:** Memory (single worker) or Redis (multi-worker) with configurable prefixes
* **Decorators:** `@rate_limit` and `@debounce` for easy handler configuration
* **Hooks:** Optional `on_rate_limited` callback for custom user feedback
* **Setup Helper:** `Sentinel.setup(dp, cfg)` wires middleware in recommended order
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
- **[Examples](../examples/)** - Complete working examples

## 🤝 Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines and setup instructions.

## 💬 Community & Support

- 💬 **[Discussions](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions)** - Questions, ideas, and community chat
- 🐛 **[Issues](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)** - Bug reports and concrete feature requests

### 🎯 Where to Get Help

| Need Help With | Go To |
|----------------|--------|
| Usage questions | 💬 **[Q&A Discussions](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions/categories/q-a)** |
| Feature suggestions | 💡 **[Ideas & Feature Requests](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions/categories/ideas-feature-requests)** |
| Bug reports | 🐛 **[Issues](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)** |
| General chat | 💬 **[General Discussion](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions/categories/general-discussion)** |
| Share projects | 🎉 **[Show and tell](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions/categories/show-and-tell)** |
| Project updates | 📢 **[Announcements](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions/categories/announcements)** |

## Security

For security issues, see [SECURITY.md](../SECURITY.md).

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.
