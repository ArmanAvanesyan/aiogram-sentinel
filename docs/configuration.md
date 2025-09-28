# Configuration Guide

Complete guide to configuring aiogram-sentinel for your needs.

## Configuration Sources

aiogram-sentinel supports multiple configuration sources in order of precedence:

1. **Code configuration** (highest priority)
2. **Environment variables**
3. **Configuration files**
4. **Default values** (lowest priority)

## Basic Configuration

### Using SentinelConfig

```python
from aiogram_sentinel import Sentinel, SentinelConfig

# Create custom configuration
config = SentinelConfig(
    throttling_default_max=5,      # 5 messages
    throttling_default_per_seconds=60,  # per minute
    debounce_default_window=3,     # 3 second debounce
    blocklist_enabled=True,        # Enable user blocking
    auth_required=False,           # Don't require registration
)

# Create Sentinel with custom config
sentinel = Sentinel(config=config)
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `throttling_default_max` | `int` | `10` | Maximum messages per window |
| `throttling_default_per_seconds` | `int` | `60` | Time window in seconds |
| `debounce_default_window` | `int` | `5` | Debounce delay in seconds |
| `blocklist_enabled` | `bool` | `True` | Enable user blocking |
| `auth_required` | `bool` | `False` | Require user registration |

## Environment Variables

Configure using environment variables:

```bash
# Rate limiting
export THROTTLING_MAX=5
export THROTTLING_WINDOW=60

# Debounce
export DEBOUNCE_WINDOW=3

# Blocklist
export BLOCKLIST_ENABLED=true

# Authentication
export AUTH_REQUIRED=false
```

```python
import os
from aiogram_sentinel import SentinelConfig

def create_config_from_env():
    return SentinelConfig(
        throttling_default_max=int(os.getenv("THROTTLING_MAX", "10")),
        throttling_default_per_seconds=int(os.getenv("THROTTLING_WINDOW", "60")),
        debounce_default_window=int(os.getenv("DEBOUNCE_WINDOW", "5")),
        blocklist_enabled=os.getenv("BLOCKLIST_ENABLED", "true").lower() == "true",
        auth_required=os.getenv("AUTH_REQUIRED", "false").lower() == "true",
    )
```

## Configuration Files

### JSON Configuration

Create `config.json`:

```json
{
  "throttling_default_max": 5,
  "throttling_default_per_seconds": 60,
  "debounce_default_window": 3,
  "blocklist_enabled": true,
  "auth_required": false
}
```

```python
import json
from aiogram_sentinel import SentinelConfig

def load_config_from_file(filename: str) -> SentinelConfig:
    with open(filename) as f:
        data = json.load(f)
    
    return SentinelConfig(**data)
```

### YAML Configuration

Create `config.yaml`:

```yaml
throttling_default_max: 5
throttling_default_per_seconds: 60
debounce_default_window: 3
blocklist_enabled: true
auth_required: false
```

```python
import yaml
from aiogram_sentinel import SentinelConfig

def load_config_from_yaml(filename: str) -> SentinelConfig:
    with open(filename) as f:
        data = yaml.safe_load(f)
    
    return SentinelConfig(**data)
```

## Storage Configuration

### Memory Storage

```python
from aiogram_sentinel import Sentinel
from aiogram_sentinel.storage import MemoryStorage

# Default memory storage
sentinel = Sentinel()

# Explicit memory storage
storage = MemoryStorage()
sentinel = Sentinel(storage=storage)
```

### Redis Storage

```python
from aiogram_sentinel import Sentinel
from aiogram_sentinel.storage import RedisStorage

# Basic Redis configuration
storage = RedisStorage("redis://localhost:6379")
sentinel = Sentinel(storage=storage)

# Advanced Redis configuration
storage = RedisStorage(
    url="redis://localhost:6379",
    namespace="my_bot",
    key_prefix="protection:",
    db=1,
    password="your_password",
    socket_timeout=5,
    socket_connect_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30,
)
```

### Redis Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | `"redis://localhost:6379"` | Redis connection URL |
| `namespace` | `str` | `"aiogram_sentinel"` | Key namespace |
| `key_prefix` | `str` | `"protection:"` | Key prefix |
| `db` | `int` | `0` | Redis database number |
| `password` | `str` | `None` | Redis password |
| `socket_timeout` | `int` | `5` | Socket timeout in seconds |
| `socket_connect_timeout` | `int` | `5` | Connection timeout in seconds |
| `retry_on_timeout` | `bool` | `True` | Retry on timeout |
| `health_check_interval` | `int` | `30` | Health check interval in seconds |

## Handler-Specific Configuration

### Using Decorators

```python
from aiogram_sentinel.decorators import sentinel_rate_limit, sentinel_debounce

@dp.message(Command("start"))
@sentinel_rate_limit(limit=3, window=60)
async def start_handler(message: Message):
    await message.answer("Welcome!")

@dp.message(Command("help"))
@sentinel_debounce(delay=2)
async def help_handler(message: Message):
    await message.answer("Help information")
```

### Using Handler Attributes

```python
@dp.message(Command("admin"))
async def admin_handler(message: Message):
    # Set custom rate limit
    message.sentinel_rate_limit = {"limit": 20, "window": 60}
    await message.answer("Admin panel")
```

## Environment-Specific Configuration

### Development

```python
# config/dev.py
from aiogram_sentinel import SentinelConfig

DEV_CONFIG = SentinelConfig(
    throttling_default_max=100,  # Very lenient for development
    throttling_default_per_seconds=60,
    debounce_default_window=1,   # Short debounce
    blocklist_enabled=False,     # Disable blocking
    auth_required=False,         # No auth required
)
```

### Production

```python
# config/prod.py
from aiogram_sentinel import SentinelConfig

PROD_CONFIG = SentinelConfig(
    throttling_default_max=5,    # Strict rate limiting
    throttling_default_per_seconds=60,
    debounce_default_window=5,   # Longer debounce
    blocklist_enabled=True,      # Enable blocking
    auth_required=True,          # Require auth
)
```

### Testing

```python
# config/test.py
from aiogram_sentinel import SentinelConfig

TEST_CONFIG = SentinelConfig(
    throttling_default_max=1000, # Very high limits for testing
    throttling_default_per_seconds=60,
    debounce_default_window=0,   # No debounce
    blocklist_enabled=False,     # No blocking
    auth_required=False,         # No auth
)
```

## Configuration Validation

### Built-in Validation

```python
from aiogram_sentinel import SentinelConfig
from aiogram_sentinel.exceptions import ConfigurationError

try:
    config = SentinelConfig(
        throttling_default_max=0,  # Invalid: must be positive
        throttling_default_per_seconds=60,
    )
except ConfigurationError as e:
    print(f"Configuration error: {e}")
```

### Custom Validation

```python
from aiogram_sentinel import SentinelConfig

class ValidatedConfig(SentinelConfig):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._validate()
    
    def _validate(self):
        if self.throttling_default_max > 1000:
            raise ValueError("Rate limit too high")
        
        if self.debounce_default_window > 300:
            raise ValueError("Debounce window too long")
```

## Configuration Precedence

Configuration is applied in this order (later overrides earlier):

1. **Default values**
2. **Environment variables**
3. **Configuration files**
4. **Code configuration**
5. **Handler-specific settings**

### Example

```python
# 1. Default: throttling_default_max = 10
# 2. Environment: THROTTLING_MAX=5
# 3. Config file: throttling_default_max = 3
# 4. Code: SentinelConfig(throttling_default_max=1)
# 5. Handler: @sentinel_rate_limit(limit=0)

# Final result: limit=0 (handler-specific wins)
```

## Hot Reloading

### File-Based Hot Reloading

```python
import asyncio
import json
from pathlib import Path
from aiogram_sentinel import SentinelConfig

class HotReloadConfig(SentinelConfig):
    def __init__(self, config_file: str):
        self.config_file = Path(config_file)
        self._load_config()
        super().__init__(**self._config_data)
    
    def _load_config(self):
        if self.config_file.exists():
            with open(self.config_file) as f:
                self._config_data = json.load(f)
        else:
            self._config_data = {}
    
    async def reload(self):
        self._load_config()
        for key, value in self._config_data.items():
            setattr(self, key, value)
```

### Usage

```python
config = HotReloadConfig("config.json")
sentinel = Sentinel(config=config)

# Reload configuration without restart
await config.reload()
```

## Best Practices

### 1. Use Environment Variables for Secrets

```python
import os

storage = RedisStorage(
    url=os.getenv("REDIS_URL", "redis://localhost:6379"),
    password=os.getenv("REDIS_PASSWORD"),
)
```

### 2. Validate Configuration Early

```python
def create_sentinel():
    try:
        config = load_config()
        return Sentinel(config=config)
    except ConfigurationError as e:
        logging.error(f"Invalid configuration: {e}")
        raise
```

### 3. Use Different Configs for Different Environments

```python
import os

def get_config():
    env = os.getenv("ENVIRONMENT", "development")
    
    if env == "production":
        return load_production_config()
    elif env == "testing":
        return load_testing_config()
    else:
        return load_development_config()
```

### 4. Document Your Configuration

```python
# config.py
"""
Configuration for aiogram-sentinel bot.

Environment Variables:
- THROTTLING_MAX: Maximum messages per window (default: 10)
- THROTTLING_WINDOW: Time window in seconds (default: 60)
- DEBOUNCE_WINDOW: Debounce delay in seconds (default: 5)
- BLOCKLIST_ENABLED: Enable user blocking (default: true)
- AUTH_REQUIRED: Require user registration (default: false)
"""
```

## Troubleshooting

### Common Configuration Issues

**Rate limiting too strict**: Increase `throttling_default_max` or `throttling_default_per_seconds`.

**Redis connection errors**: Check Redis URL, password, and network connectivity.

**Configuration not applied**: Verify configuration precedence and handler-specific overrides.

**Validation errors**: Check parameter types and value ranges.

### Debug Configuration

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Log configuration
config = SentinelConfig()
logging.info(f"Configuration: {config.__dict__}")
```
