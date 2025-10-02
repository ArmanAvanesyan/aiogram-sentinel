# Installation

This guide covers how to install aiogram-sentinel and its dependencies.

## Requirements

- Python 3.10 or higher
- aiogram v3.0.0 or higher

## Basic Installation

Install the core package:

```bash
pip install aiogram-sentinel
```

## Installation with Redis Support

For production deployments with Redis backend:

```bash
pip install aiogram-sentinel[redis]
```

This installs the additional `redis` dependency required for the Redis storage backend.

## Development Installation

For development and contributing:

```bash
git clone https://github.com/ArmanAvanesyan/aiogram-sentinel.git
cd aiogram-sentinel
pip install -e ".[dev]"
```

This installs the package in editable mode with all development dependencies.

## Using uv (Recommended)

If you're using `uv` for package management:

```bash
# Basic installation
uv add aiogram-sentinel

# With Redis support
uv add "aiogram-sentinel[redis]"

# Development
uv add -e ".[dev]"
```

##<｜tool▁sep｜>verification

Verify the installation:

```python
import aiogram_sentinel
print(aiogram_sentinel.__version__)
```

## Next Steps

- See [Quickstart](quickstart.md) to get started
- Check [Configuration](configuration.md) for setup options
- Browse [Examples](../examples/) for complete working examples
