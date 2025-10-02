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
    backend="memory",              # Use memory storage
)

# Setup with custom config
router, infra = await Sentinel.setup(dp, config)
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `throttling_default_max` | `int` | `5` | Maximum messages per window |
| `throttling_default_per_seconds` | `int` | `10` | Time window in seconds |
| `debounce_default_window` | `int` | `2` | Debounce delay in seconds |
| `backend` | `str` | `"memory"` | Storage backend ("memory" or "redis") |
| `redis_url` | `str` | `"redis://localhost:6379"` | Redis connection URL |
| `redis_prefix` | `str` | `"sentinel"` | Redis key prefix |
| `auto_block_on_limit` | `bool` | `True` | Auto-block users who exceed limits (unused) |

## Environment Variables

Configure using environment variables:

```bash
# Rate limiting
export THROTTLING_MAX=5
export THROTTLING_WINDOW=60

# Debounce
export DEBOUNCE_WINDOW=3

# Backend
export BACKEND=redis
export REDIS_URL=redis://localhost:6379
export REDIS_PREFIX=mybot:
```

```python
import os
from aiogram_sentinel import SentinelConfig

def create_config_from_env():
    return SentinelConfig(
        throttling_default_max=int(os.getenv("THROTTLING_MAX", "5")),
        throttling_default_per_seconds=int(os.getenv("THROTTLING_WINDOW", "10")),
        debounce_default_window=int(os.getenv("DEBOUNCE_WINDOW", "2")),
        backend=os.getenv("BACKEND", "memory"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        redis_prefix=os.getenv("REDIS_PREFIX", "sentinel"),
    )
```

## Configuration Files

### JSON Configuration

Create `config.json`:

```json
{
  "throttling_default_max": 5,
  "throttling_default_per_seconds": 10,
  "debounce_default_window": 2,
  "backend": "redis",
  "redis_url": "redis://localhost:6379",
  "redis_prefix": "mybot"
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
throttling_default_per_seconds: 10
debounce_default_window: 2
backend: redis
redis_url: redis://localhost:6379
redis_prefix: mybot
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
from aiogram_sentinel import Sentinel, SentinelConfig

# Default memory storage
config = SentinelConfig(backend="memory")
router, infra = await Sentinel.setup(dp, config)
```

### Redis Storage

```python
from aiogram_sentinel import Sentinel, SentinelConfig

# Basic Redis configuration
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_prefix="mybot",
)
router, infra = await Sentinel.setup(dp, config)

# Advanced Redis configuration
config = SentinelConfig(
    backend="redis",
    redis_url="redis://username:password@localhost:6379/1",
    redis_prefix="mybot:prod",
)
```

### Redis Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `redis_url` | `str` | `"redis://localhost:6379"` | Redis connection URL |
| `redis_prefix` | `str` | `"sentinel"` | Key prefix for all Redis keys |

## Handler-Specific Configuration

### Using Decorators

```python
from aiogram_sentinel import rate_limit, debounce

@router.message()
@rate_limit(3, 60)  # 3 messages per minute
@debounce(2.0)      # 2 second debounce
async def start_handler(message: Message):
    await message.answer("Welcome!")

@router.message()
@rate_limit(10, 60)  # 10 messages per minute
@debounce(1.0)       # 1 second debounce
async def help_handler(message: Message):
    await message.answer("Help information")
```

### Using Scopes

```python
@router.message()
@rate_limit(5, 60, scope="commands")  # Shared limit for all commands
@debounce(1.0, scope="commands")
async def command_handler(message: Message):
    await message.answer("Command executed!")

@router.message()
@rate_limit(5, 60, scope="commands")  # Same scope = shared limit
@debounce(1.0, scope="commands")
async def another_command_handler(message: Message):
    await message.answer("Another command!")
```

## Environment-Specific Configuration

### Development

```python
# config/dev.py
from aiogram_sentinel import SentinelConfig

DEV_CONFIG = SentinelConfig(
    throttling_default_max=100,  # Very lenient for development
    throttling_default_per_seconds=10,
    debounce_default_window=1,   # Short debounce
    backend="memory",            # Use memory for development
)
```

### Production

```python
# config/prod.py
from aiogram_sentinel import SentinelConfig

PROD_CONFIG = SentinelConfig(
    throttling_default_max=5,    # Strict rate limiting
    throttling_default_per_seconds=10,
    debounce_default_window=2,   # Standard debounce
    backend="redis",             # Use Redis for production
    redis_url="redis://localhost:6379",
    redis_prefix="mybot:prod",
)
```

### Testing

```python
# config/test.py
from aiogram_sentinel import SentinelConfig

TEST_CONFIG = SentinelConfig(
    throttling_default_max=1000, # Very high limits for testing
    throttling_default_per_seconds=10,
    debounce_default_window=0,   # No debounce
    backend="memory",            # Use memory for testing
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
# 5. Handler: @rate_limit(0, 60)

# Final result: limit=0 (handler-specific wins)
```

## Hooks Configuration

### Rate Limiting Hook

```python
async def on_rate_limited(event, data, retry_after):
    """Called when rate limit is exceeded."""
    await event.answer(f"⏰ Rate limited! Try again in {int(retry_after)} seconds.")

# Add the hook
Sentinel.add_hooks(router, infra, config, on_rate_limited=on_rate_limited)
```

### Custom Hook Example

```python
import logging

logger = logging.getLogger(__name__)

async def on_rate_limited(event, data, retry_after):
    """Custom rate limiting hook with logging."""
    user_id = getattr(event, 'from_user', {}).id if hasattr(event, 'from_user') else 'unknown'
    handler_name = data.get('handler', 'unknown')
    
    logger.warning(f"Rate limited: user={user_id}, handler={handler_name}, retry_after={retry_after}")
    
    # Send custom message
    if hasattr(event, 'answer'):
        await event.answer(f"🚫 Rate limited! Try again in {int(retry_after)} seconds.")

# Add the hook
Sentinel.add_hooks(router, infra, config, on_rate_limited=on_rate_limited)
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
router, infra = await Sentinel.setup(dp, config)

# Reload configuration without restart
await config.reload()
```

## Best Practices

### 1. Use Environment Variables for Secrets

```python
import os

config = SentinelConfig(
    backend="redis",
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
    redis_prefix=os.getenv("REDIS_PREFIX", "sentinel"),
)
```

### 2. Validate Configuration Early

```python
def create_sentinel():
    try:
        config = load_config()
        return Sentinel.setup(dp, config)
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
- THROTTLING_MAX: Maximum messages per window (default: 5)
- THROTTLING_WINDOW: Time window in seconds (default: 10)
- DEBOUNCE_WINDOW: Debounce delay in seconds (default: 2)
- BACKEND: Storage backend ("memory" or "redis", default: "memory")
- REDIS_URL: Redis connection URL (default: "redis://localhost:6379")
- REDIS_PREFIX: Redis key prefix (default: "sentinel")
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

## Advanced Configuration Examples

### Multi-Environment Setup

```python
import os
from aiogram_sentinel import Sentinel, SentinelConfig

def create_config():
    env = os.getenv("ENVIRONMENT", "development")
    
    if env == "production":
        return SentinelConfig(
            backend="redis",
            redis_url=os.getenv("REDIS_URL"),
            redis_prefix="mybot:prod",
            throttling_default_max=5,
            throttling_default_per_seconds=10,
            debounce_default_window=2,
        )
    elif env == "staging":
        return SentinelConfig(
            backend="redis",
            redis_url=os.getenv("REDIS_URL"),
            redis_prefix="mybot:staging",
            throttling_default_max=10,
            throttling_default_per_seconds=10,
            debounce_default_window=2,
        )
    else:  # development
        return SentinelConfig(
            backend="memory",
            throttling_default_max=100,
            throttling_default_per_seconds=10,
            debounce_default_window=1,
        )

# Use the configuration
config = create_config()
router, infra = await Sentinel.setup(dp, config)
```

### Dynamic Configuration

```python
class DynamicConfig(SentinelConfig):
    """Configuration that can be updated at runtime."""
    
    def __init__(self):
        super().__init__()
        self._rate_limits: dict[str, tuple] = {}
    
    def set_rate_limit(self, handler_name: str, limit: int, window: int):
        """Set rate limit for specific handler."""
        self._rate_limits[handler_name] = (limit, window)
    
    def get_rate_limit(self, handler_name: str) -> tuple[int, int]:
        """Get rate limit for handler."""
        return self._rate_limits.get(handler_name, (self.throttling_default_max, self.throttling_default_per_seconds))

# Use dynamic configuration
config = DynamicConfig()
config.set_rate_limit("start", 3, 60)
config.set_rate_limit("help", 5, 60)
router, infra = await Sentinel.setup(dp, config)
```