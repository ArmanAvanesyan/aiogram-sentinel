# aiogram-sentinel

<p align="center">
  <!-- Essentials -->
  <a href="https://github.com/ArmanAvanesyan/aiogram-sentinel/actions/workflows/ci.yml">
    <img alt="CI" src="https://github.com/ArmanAvanesyan/aiogram-sentinel/actions/workflows/ci.yml/badge.svg?branch=main">
  </a>
  <a href="https://pypi.org/project/aiogram-sentinel/">
    <img alt="PyPI" src="https://img.shields.io/pypi/v/aiogram-sentinel.svg">
  </a>
  <a href="https://pypi.org/project/aiogram-sentinel/">
    <img alt="Python versions" src="https://img.shields.io/pypi/pyversions/aiogram-sentinel.svg">
  </a>
  <a href="https://armanavanesyan.github.io/aiogram-sentinel/">
    <img alt="Docs" src="https://github.com/ArmanAvanesyan/aiogram-sentinel/actions/workflows/docs.yml/badge.svg?branch=main">
  </a>
  <a href="LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/ArmanAvanesyan/aiogram-sentinel.svg">
  </a>
</p>

<details>
<summary>More badges</summary>

<p>
  <a href="https://app.codecov.io/gh/ArmanAvanesyan/aiogram-sentinel">
    <img alt="Coverage" src="https://codecov.io/gh/ArmanAvanesyan/aiogram-sentinel/branch/main/graph/badge.svg">
  </a>
  <a href="https://docs.astral.al/ruff/">
    <img alt="Ruff" src="https://img.shields.io/badge/lint-ruff-%2300A1D6">
  </a>
  <a href="https://github.com/microsoft/pyright">
    <img alt="Pyright" src="https://img.shields.io/badge/types-pyright-blue">
  </a>
  <a href="https://pepy.tech/project/aiogram-sentinel">
    <img alt="Downloads" src="https://static.pepy.tech/badge/aiogram-sentinel/month">
  </a>
</p>

</details>

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

👉 **[Full Documentation](https://armanavanesyan.github.io/aiogram-sentinel/)** ← Start here!

- **[Quickstart](docs/quickstart.md)** - Get started in 5 minutes
- **[Configuration](docs/configuration.md)** - Complete configuration guide
- **[API Reference](docs/api/)** - Full API documentation
- **[Tutorials](docs/tutorials/)** - Step-by-step guides
- **[Performance](docs/performance.md)** - Benchmarks and optimization
- **[Examples](examples/)** - Complete working examples

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and setup instructions.

## 🔒 Security

For security issues, see [SECURITY.md](.github/SECURITY.md).

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built for [aiogram v3](https://github.com/aiogram/aiogram) - Modern Telegram Bot API framework
- Inspired by the need for robust bot protection in production environments
