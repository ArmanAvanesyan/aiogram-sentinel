# Installation

This guide covers installing aiogram-cmds and its dependencies.

## 📦 Basic Installation

Install aiogram-cmds using pip:

```bash
pip install aiogram-cmds
```

## 🔧 Requirements

### Python Version
- **Python 3.10+** (required)
- **Python 3.11, 3.12, 3.13** (recommended)

### Core Dependencies
- **aiogram >= 3.0.0, < 4** - Telegram Bot API framework
- **pydantic >= 2.0.0, < 3** - Data validation and settings

### Optional Dependencies
- **redis >= 5.0.8, < 8** - Client for application-owned integrations (install with `[redis]` extra)

## 🚀 Installation Options

### Standard Installation
```bash
pip install aiogram-cmds
```

### Optional Redis client
For application-owned caching or coordination:

```bash
pip install aiogram-cmds[redis]
```

The extra installs only a client. It does not add command caching, distributed
locks, persistence or multi-worker safety. Applications implement these explicitly.

### Development Installation
For contributing to the project:

```bash
git clone https://github.com/ArmanAvanesyan/aiogram-cmds.git
cd aiogram-cmds
pip install -e ".[dev]"
```

### Using uv (Recommended)
For faster dependency resolution:

```bash
uv add aiogram-cmds
# or with Redis
uv add "aiogram-cmds[redis]"
```

### Using Poetry
```bash
poetry add aiogram-cmds
# or with Redis
poetry add "aiogram-cmds[redis]"
```

## 🔍 Verification

Verify your installation:

```python
import aiogram_cmds
print(aiogram_cmds.__version__)
```

Or test the basic functionality:

```python
from aiogram_cmds import CommandScopeManager
from aiogram import Bot

# This should work without errors
bot = Bot("123456:EXAMPLE_TOKEN_FOR_LOCAL_VALIDATION_ONLY")
manager = CommandScopeManager(bot)
print("✅ aiogram-cmds installed successfully!")
```

## 🐳 Docker Installation

### Using Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "bot.py"]
```

### Using Docker Compose
```yaml
version: '3.8'
services:
  bot:
    build: .
    environment:
      - BOT_TOKEN=your_bot_token
    depends_on:
      - redis
  redis:
    image: redis:7-alpine
```

## 🔧 Development Setup

### Prerequisites
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Git

### Setup Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ArmanAvanesyan/aiogram-cmds.git
   cd aiogram-cmds
   ```

2. **Create virtual environment:**
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install in development mode:**
   ```bash
   uv sync --all-extras --all-groups --frozen
   ```

4. **Run the contribution checks:**
   ```bash
   uv run --frozen ruff check .
   uv run --frozen pyright
   uv run --frozen pytest tests/unit tests/integration
   ```

No pre-commit hooks are configured. See the
[contribution guide](https://github.com/ArmanAvanesyan/aiogram-cmds/blob/main/CONTRIBUTING.md)
for documentation and packaging checks.

## 📋 System Requirements

### Minimum Requirements
- **RAM**: 128 MB
- **Storage**: 50 MB
- **Network**: Internet connection for Telegram API

### Recommended Requirements
- **RAM**: 512 MB
- **Storage**: 100 MB
- **CPU**: 1 core
- **Network**: Stable internet connection

### Production Requirements
- **RAM**: 1 GB+
- **Storage**: 500 MB+
- **CPU**: 2+ cores
- **Network**: High-speed, reliable connection
- **Redis**: Optional application infrastructure; no backend is implemented here

## 🚨 Troubleshooting

### Common Installation Issues

#### ImportError: No module named 'aiogram_cmds'
```bash
# Make sure you're in the right environment
which python
pip list | grep aiogram-cmds

# Reinstall if needed
pip uninstall aiogram-cmds
pip install aiogram-cmds
```

#### Version Conflicts
```bash
# Check for conflicting packages
pip list | grep aiogram
pip list | grep pydantic

# Upgrade aiogram if needed
pip install --upgrade aiogram>=3.0.0
```

#### Redis Connection Issues
```bash
# Test Redis connection
python -c "import redis; r = redis.Redis(); print(r.ping())"

# Install Redis if missing
# Ubuntu/Debian
sudo apt-get install redis-server

# macOS
brew install redis

# Windows
# Download from https://redis.io/download
```

### Platform-Specific Issues

#### Windows
- Use PowerShell or Command Prompt as Administrator
- Install Visual C++ Build Tools if compilation fails
- Use `python -m pip` instead of `pip` if PATH issues occur

#### macOS
- Install Xcode Command Line Tools: `xcode-select --install`
- Use Homebrew for system dependencies: `brew install python`

#### Linux
- Install Python development headers: `sudo apt-get install python3-dev`
- Install build essentials: `sudo apt-get install build-essential`

## 🔄 Upgrading

### Upgrade aiogram-cmds
```bash
pip install --upgrade aiogram-cmds
```

### Upgrade with Redis support
```bash
pip install --upgrade "aiogram-cmds[redis]"
```

### Check current version
```python
import aiogram_cmds
print(aiogram_cmds.__version__)
```

## 📚 Next Steps

After installation:

1. **[Quickstart Guide](quickstart.md)** - Get started in 5 minutes
2. **[Configuration](configuration.md)** - Configure your bot
3. **[Examples](https://github.com/ArmanAvanesyan/aiogram-cmds/tree/main/examples)** - See working examples
4. **[API Reference](api/core.md)** - Explore the API

## 💡 Tips

- Use virtual environments to avoid dependency conflicts
- Pin your dependencies in production: `pip freeze > requirements.txt`
- Test your installation with the verification code above
- Keep aiogram-cmds updated for bug fixes and new features
- Coordinate updates between workers explicitly in your application; the Redis extra only installs a client

---

**Installation complete?** Head to the [Quickstart Guide](quickstart.md) to get started!
