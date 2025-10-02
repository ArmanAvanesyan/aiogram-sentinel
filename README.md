# aiogram-sentinel

[![CI](https://img.shields.io/github/actions/workflow/status/ArmanAvanesyan/aiogram-sentinel/ci.yml?branch=main&label=CI)](../../actions)
[![PyPI](https://img.shields.io/pypi/v/aiogram-sentinel.svg)](https://pypi.org/project/aiogram-sentinel/)
[![Python](https://img.shields.io/pypi/pyversions/aiogram-sentinel.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/badge/lint-ruff-informational)](https://github.com/astral-sh/ruff)

**Rate limiting and debouncing middleware for aiogram v3** - Protect your Telegram bots from spam and abuse with powerful middleware and storage backends.

## ✨ Features

* **Rate Limiting:** Per-user/handler scopes with sliding window algorithm
* **Debouncing:** Suppress duplicate messages/callbacks within a configurable window
* **Storage Backends:** Memory (single worker) or Redis (multi-worker) with configurable prefixes
* **Decorators:** `@rate_limit` and `@debounce` for easy handler configuration
* **Hooks:** Optional `on_rate_limited` callback for custom user feedback
* **Setup Helper:** `Sentinel.setup(dp, cfg)` wires middleware in recommended order
* **Typed, async-first, production-ready.**

## 📦 Installation

```bash
# Basic installation
pip install aiogram-sentinel

# With Redis support
pip install aiogram-sentinel[redis]
```

## ⚡ Quick Start

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

## 📚 Documentation

- **[Quickstart](docs/quickstart.md)** - Get started in 5 minutes
- **[Configuration](docs/configuration.md)** - Complete configuration guide
- **[API Reference](docs/api/)** - Full API documentation
- **[Tutorials](docs/tutorials/)** - Step-by-step guides
- **[Performance](docs/performance.md)** - Benchmarks and optimization
- **[Examples](examples/)** - Complete working examples

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and setup instructions.

## 🔒 Security

For security issues, see [SECURITY.md](SECURITY.md).

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built for [aiogram v3](https://github.com/aiogram/aiogram) - Modern Telegram Bot API framework
- Inspired by the need for robust bot protection in production environments
