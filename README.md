# aiogram-sentinel

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Edge hygiene library for aiogram v3** - Protect your Telegram bots from spam, abuse, and unwanted behavior with powerful middleware and storage backends.

## 🚀 Features

### 🛡️ **Protection Middlewares**
- **Blocking**: Early user blocking with configurable blocklists
- **Authentication**: User registration and context management
- **Debouncing**: Prevent duplicate message processing
- **Throttling**: Rate limiting with customizable windows and limits

### 🔧 **Storage Backends**
- **Memory**: Fast in-memory storage for development and testing
- **Redis**: Production-ready persistent storage with namespacing

### 🎯 **Easy Integration**
- **One-call setup**: `Sentinel.setup(dp, config)` configures everything
- **Decorators**: `@rate_limit`, `@debounce`, `@require_registered`
- **Hooks**: Customizable callbacks for all events

### 📊 **Membership Management**
- **Auto-sync**: Blocklist synchronization with bot membership changes
- **Event hooks**: Handle user block/unblock events

## 📦 Installation

```bash
# Basic installation
pip install aiogram-sentinel

# With Redis support
pip install aiogram-sentinel[redis]
```

## ⚡ Quick Start

### 1. Basic Setup

```python
from aiogram import Bot, Dispatcher
from aiogram_sentinel import Sentinel, SentinelConfig

# Create bot and dispatcher
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# Configure aiogram-sentinel
config = SentinelConfig(
    backend="memory",  # or "redis" for production
    default_rate_limit=10,  # 10 messages per window
    default_rate_window=60,  # 60 second window
)

# Setup with one call
router, backends = Sentinel.setup(dp, config)

# Start your bot
await dp.start_polling(bot)
```

### 2. Using Decorators

```python
from aiogram_sentinel import rate_limit, debounce, require_registered
from aiogram.types import Message

@rate_limit(limit=5, window=30)  # 5 messages per 30 seconds
@debounce(delay=1.0)             # 1 second debounce
@require_registered()            # Requires user registration
async def protected_handler(message: Message):
    await message.answer("This is a protected command!")
```

### 3. Custom Hooks

```python
async def on_rate_limited(event, data, retry_after):
    """Called when user hits rate limit"""
    await event.answer(f"⏰ Please wait {retry_after:.1f} seconds")

async def resolve_user(event, data):
    """Custom user validation"""
    if event.from_user.is_bot:
        return None  # Block bot users
    return {"user_id": event.from_user.id, "username": event.from_user.username}

# Setup with hooks
router, backends = Sentinel.setup(
    dp, config,
    on_rate_limited=on_rate_limited,
    resolve_user=resolve_user,
)
```

## 📚 Documentation

- **[Architecture](docs/ARCHITECTURE.md)** - System design and components
- **[Hooks](docs/HOOKS.md)** - Available hooks and customization
- **[Testing](docs/TESTING.md)** - Testing approach and examples
- **[Security](docs/SECURITY.md)** - Security considerations
- **[Examples](examples/)** - Complete working examples

## 🎯 Use Cases

### **Spam Protection**
```python
# Block users who send too many messages
@rate_limit(limit=3, window=60)
async def message_handler(message: Message):
    await message.answer("Message received!")
```

### **Duplicate Prevention**
```python
# Prevent processing duplicate messages
@debounce(delay=2.0)
async def command_handler(message: Message):
    await message.answer("Command processed!")
```

### **User Management**
```python
# Require user registration for sensitive commands
@require_registered()
async def admin_command(message: Message):
    await message.answer("Admin command executed!")
```

### **Membership Sync**
```python
# Automatically block users who block your bot
async def on_user_blocked(user_id: int, username: str, data: dict):
    print(f"User {username} blocked the bot")
    # Custom logic: log to database, notify admins, etc.
```

## 🔧 Configuration

### **Memory Backend** (Development)
```python
config = SentinelConfig(
    backend="memory",
    default_rate_limit=10,
    default_rate_window=60,
    default_debounce_delay=1.0,
)
```

### **Redis Backend** (Production)
```python
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_prefix="my_bot:",
    default_rate_limit=20,
    default_rate_window=60,
)
```

## 🏗️ Architecture

aiogram-sentinel follows a modular architecture:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Middlewares   │    │   Storage        │    │     Router      │
│                 │    │   Backends       │    │                 │
│ • Blocking      │◄──►│ • Memory         │    │ • Membership    │
│ • Auth          │    │ • Redis          │    │ • Hooks         │
│ • Debouncing    │    │                  │    │                 │
│ • Throttling    │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │  Setup Helper   │
                    │                 │
                    │ Sentinel.setup  │
                    └─────────────────┘
```

## 🧪 Examples

Check out the [examples/](examples/) directory for complete working bots:

- **[minimal_bot.py](examples/minimal_bot.py)** - Complete example with all features
- **[README.md](examples/README.md)** - Example documentation and usage

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built for [aiogram v3](https://github.com/aiogram/aiogram) - Modern Telegram Bot API framework
- Inspired by the need for robust bot protection in production environments

## Development

### Project Structure

This project follows a modular architecture with clear separation of concerns:

- **Storage Backends**: Memory and Redis implementations for rate limiting, debouncing, and user management
- **Middlewares**: Blocking, authentication, debouncing, and throttling middleware
- **Router**: Membership management with automatic blocklist synchronization
- **Setup Helper**: Simple one-call configuration for all components

### Issue Labels

We use a structured labeling system for better organization:

**Area Labels:**
- `area:storage` - Storage backends and data persistence
- `area:middleware` - Middleware implementations  
- `area:router` - Router and routing logic
- `area:setup` - Project setup and configuration
- `area:docs` - Documentation
- `area:ci` - CI/CD and automation
- `area:examples` - Example code and demos
- `area:tests` - Testing infrastructure

**Type Labels:**
- `type:feat` - New features
- `type:fix` - Bug fixes
- `type:docs` - Documentation changes
- `type:refactor` - Code refactoring
- `type:ci` - CI/CD changes
- `type:test` - Test-related changes

**Priority Labels:**
- `priority:p0` - Release blocking (must be in v0.1.0)
- `priority:p1` - Important for v0.1.0
- `priority:p2` - Nice to have, can be deferred

### Development Workflow

1. **Small PRs** matching individual issues
2. **Conventional Commits** for all commits
3. **Definition of Done** per PR: Code + tests + docs + CI green
4. **Sequencing**: Follow dependency chain strictly

### Milestones

- **v0.1.0** - First public release with core features, documentation, CI, and examples
- **v0.2.0** - Hooks expansion, redis prefix, notifier polish  
- **v1.0.0** - Token bucket, metrics hooks, stable API commitment

## License

MIT License - see [LICENSE](LICENSE) file for details.
