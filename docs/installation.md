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

## Verification

Verify the installation:

```python
import aiogram_sentinel
print(aiogram_sentinel.__version__)
```

## Next Steps

- See [Quickstart](quickstart.md) to get started
- Check [Configuration](configuration.md) for setup options
- Browse [Examples](https://github.com/ArmanAvanesyan/aiogram-sentinel/tree/main/examples) for complete working examples

## Optional dependencies and router ownership

The base installation uses in-process memory storage and does not import Redis
or Sentry. Select Redis explicitly with `SentinelConfig(backend="redis")` after
installing `aiogram-sentinel[redis]` (redis-py 5.0.8 through 7.x). Redis clients
created by the factory are shared by the two backends; applications own their
shutdown. Memory state is process-local and disappears on restart.

`await Sentinel.setup(...)` installs one chain on an unattached router. Duplicate
installation is rejected. `Sentinel.add_hooks(router, infra, cfg, ...)` accepts
the exact infrastructure and configuration returned/used by that installation
and updates only its rate-limit callback. Existing application guards and error
middleware remain in place. Pass `None` to remove a callback. Configure errors
with the per-setup `error_config` argument; legacy `Sentinel.use_errors` applies
to the next successful setup only and is unsuitable for concurrent setup code.
