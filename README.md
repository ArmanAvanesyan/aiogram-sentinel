# aiogram-cmds

[![CI](https://github.com/ArmanAvanesyan/aiogram-cmds/workflows/CI/badge.svg)](https://github.com/ArmanAvanesyan/aiogram-cmds/actions)
[![PyPI](https://img.shields.io/pypi/v/aiogram-cmds.svg)](https://pypi.org/project/aiogram-cmds/)
[![Python versions](https://img.shields.io/pypi/pyversions/aiogram-cmds.svg)](https://pypi.org/project/aiogram-cmds/)
[![License](https://img.shields.io/pypi/l/aiogram-cmds.svg)](https://pypi.org/project/aiogram-cmds/)

**Command management library for aiogram v3** - Manage Telegram bot commands with i18n support, user profiles, and dynamic scopes.

## ✨ Features

* **Simple & Advanced Modes**: Start simple, scale to complex configurations
* **i18n Integration**: Built-in support for aiogram i18n with fallback handling
* **User Profiles**: Dynamic command sets based on user status (guest, registered, etc.)
* **Multiple Scopes**: Support for all Telegram command scopes (private, group, admin, etc.)
* **Auto-Setup**: One-call setup with sensible defaults
* **Type-Safe**: Full type hints and strict type checking
* **Verified behavior**: Contract tests, CI and documented failure semantics

## 📦 Installation

```bash
# Basic installation
pip install aiogram-cmds

# Optional Redis client for application-owned integrations
pip install aiogram-cmds[redis]
```

The Redis extra installs a client only. This library provides no Redis backend,
distributed lock, command cache or multi-worker coordination. Applications own
those concerns; installing the extra does not make updates atomic.

## ⚡ Quick Start

### Auto-Setup (Recommended)

```python
from aiogram import Bot, Dispatcher
from aiogram_cmds.auto_setup import setup_commands_auto

async def on_startup():
    # Automatically set up commands with sensible defaults
    command_manager = await setup_commands_auto(bot)
    # Commands are ready to use!

# Your handlers
@dp.message(Command("start"))
async def handle_start(message: Message):
    await message.answer("Welcome! Use /help to see available commands.")
```

### Application-selected profiles (recommended)

```python
from aiogram_cmds import CmdsConfig, CommandDef, ProfileDef, ScopeDef, MenuButtonDef

# Define your command configuration
config = CmdsConfig(
    languages=["en", "ru", "es"],
    commands={
        "start": CommandDef(i18n_key="start.desc"),
        "help": CommandDef(i18n_key="help.desc"),
        "profile": CommandDef(i18n_key="profile.desc"),
        "admin": CommandDef(i18n_key="admin.desc"),
    },
    profiles={
        "guest": ProfileDef(include=["start", "help"]),
        "user": ProfileDef(include=["start", "help", "profile"]),
        "admin": ProfileDef(include=["start", "help", "profile", "admin"]),
    },
    scopes=[
        ScopeDef(scope="all_private_chats", profile="guest"),
        ScopeDef(scope="chat", chat_id=12345, profile="admin"),
    ],
    menu_button=MenuButtonDef(mode="commands"),
)

# Select profiles in your application using its own roles and state.
manager = CommandScopeManager(bot, config=config)
await manager.setup_all()
await manager.update_profile(user_id=12345, profile="admin", language="en")
```

### Legacy flag-based compatibility

```python
from aiogram import Bot, Dispatcher
from aiogram_cmds import CommandScopeManager, load_settings, build_translator_from_i18n

# Load settings from pyproject.toml or use defaults
settings = load_settings()
translator = build_translator_from_i18n(i18n)  # Your aiogram i18n instance

# Create manager
manager = CommandScopeManager(bot, settings=settings, translator=translator)

# Set up all command scopes
await manager.setup_all()

# Update user commands dynamically
await manager.update_user_commands(
    user_id=12345,
    is_registered=True,
    has_vehicle=False,
    user_language="en"
)
```

### Failure handling

Manager methods return `True` only after all Telegram operations finish. They
propagate the original error by default. Code that relied on the old silent
failure behavior can opt into `CommandScopeManager(bot, best_effort=True)` and
check the returned boolean (`False` on failure). Cancellation always propagates.
`setup_commands_auto` also propagates startup failures.

A multi-scope update is sequential: an error can leave earlier scopes updated.
There is no rollback or automatic retry. Retry deliberately after inspecting the
error; command-setting calls replace the target scope's commands.

`Flags` and `update_user_commands` remain supported for legacy integrations.
Generic applications should select a profile themselves and use `update_profile`.

## 🎯 Use Cases

### E-commerce Bot
```python
# Different commands for different user states
profiles = {
    "visitor": ProfileDef(include=["start", "catalog", "help"]),
    "customer": ProfileDef(include=["start", "catalog", "cart", "orders", "help"]),
    "vip": ProfileDef(include=["start", "catalog", "cart", "orders", "vip_offers", "help"]),
}
```

### Admin Bot
```python
# Admin commands only for specific users
scopes = [
    ScopeDef(scope="all_private_chats", profile="user"),
    ScopeDef(scope="chat_member", chat_id=12345, user_id=67890, profile="admin"),
]
```

### Multi-Language Bot
```python
# Commands in multiple languages
config = CmdsConfig(
    languages=["en", "ru", "es", "fr"],
    commands={
        "start": CommandDef(i18n_key="commands.start"),
        "help": CommandDef(i18n_key="commands.help"),
    }
)
```

## 📚 Documentation

👉 **[Full Documentation](https://aiogram-cmds.dev)** ← Start here!

* **[Quickstart](https://aiogram-cmds.dev/quickstart/)** - Get started in 5 minutes
* **[Configuration](https://aiogram-cmds.dev/configuration/)** - Complete configuration guide
* **[API Reference](https://aiogram-cmds.dev/api/)** - Full API documentation
* **[Tutorials](https://aiogram-cmds.dev/tutorials/)** - Step-by-step guides
* **[Examples](https://aiogram-cmds.dev/examples/)** - Complete working examples

## 🏗️ Architecture

aiogram-cmds provides three levels of complexity:

1. **Auto-Setup**: Zero configuration, works out of the box
2. **Simple Mode**: Settings-based configuration with policies
3. **Advanced Mode**: Full control with profiles, scopes, and custom resolvers

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Auto-Setup    │    │   Simple Mode    │    │  Advanced Mode  │
│                 │    │                  │    │                 │
│ setup_commands_ │    │ CmdsSettings +   │    │ CmdsConfig +    │
│ auto()          │    │ CommandPolicy    │    │ ProfileResolver │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌──────────────────┐
                    │ CommandScopeMgr  │
                    │                  │
                    │ • setup_all()    │
                    │ • update_user()  │
                    │ • clear_user()   │
                    └──────────────────┘
```

## 🤝 Contributing

We welcome contributions! See our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/ArmanAvanesyan/aiogram-cmds.git
cd aiogram-cmds

# Set up development environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Run linting
uv run ruff check .
uv run ruff format .
```

## 💬 Community & Support

* 💬 **[Discussions](https://github.com/ArmanAvanesyan/aiogram-cmds/discussions)** - Questions, ideas, and community chat
* 🐛 **[Issues](https://github.com/ArmanAvanesyan/aiogram-cmds/issues)** - Bug reports and feature requests
* 📖 **[Documentation](https://aiogram-cmds.dev)** - Complete guides and API reference

## 🔒 Security

For security issues, see [SECURITY.md](SECURITY.md).

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

* Built for [aiogram v3](https://github.com/aiogram/aiogram) - Modern Telegram Bot API framework
* Inspired by the need for robust command management in production environments

## 📊 Project Status

- ✅ **Core Features**: Command management, i18n, profiles, scopes
- ✅ **Documentation**: Comprehensive guides and API reference
- ✅ **Testing**: Unit, integration, and performance tests
- ✅ **CI**: Automated verification; deliberate package releases and manual documentation publication
- 🚧 **Examples**: Working bot examples (in progress)
- 🔮 **Future**: Rate limiting, caching, advanced analytics

---

**Made with ❤️ for the aiogram community**

## Contributing and maintenance

See [CONTRIBUTING.md](CONTRIBUTING.md) for repository conventions and checks,
[SECURITY.md](SECURITY.md) for private vulnerability reporting, and
[docs/releasing.md](docs/releasing.md) for maintainer release instructions.

## Compatibility and 0.2 migration

| Component | Supported / tested |
| --- | --- |
| Python | 3.10–3.13 in CI |
| aiogram | >=3.0.0,<4; minimum 3.0.0 and latest resolvable 3.x in CI |
| Redis | Optional client extra >=5.0.8,<8; no Redis server/backend is implemented |

See [the 0.2 migration guide](docs/migration-0.2.md) for independent rendering
locale/menu slots, default-language fallback, explicit language cleanup,
confirmed payload fingerprints and partial batch outcomes. Run
`uv run python examples/application_profiles.py --dry-run` for a network-free
example. The library never configures application logging.
