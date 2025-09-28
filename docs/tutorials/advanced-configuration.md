# Tutorial: Advanced Configuration

**Goal**: Master advanced configuration options for aiogram-sentinel.

**What you'll build**: A bot with custom middleware, storage backends, and advanced protection settings.

## Prerequisites

- Completed [Basic Protection Tutorial](basic-protection.md)
- Understanding of aiogram middleware
- Basic knowledge of configuration patterns

## Step 1: Custom Configuration Class

Create a custom configuration class:

```python
from aiogram_sentinel import SentinelConfig
from typing import Callable, Any

class MyBotConfig(SentinelConfig):
    """Custom configuration for my bot."""
    
    def __init__(self):
        super().__init__(
            # Rate limiting settings
            throttling_default_max=10,
            throttling_default_per_seconds=60,
            
            # Debounce settings
            debounce_default_window=3,
            
            # Blocklist settings
            blocklist_enabled=True,
            
            # Authentication settings
            auth_required=False,
        )
    
    def get_rate_limit_for_handler(self, handler_name: str) -> tuple[int, int]:
        """Custom rate limiting per handler."""
        limits = {
            "start": (5, 60),      # 5 messages per minute
            "help": (3, 60),       # 3 messages per minute
            "admin": (20, 60),     # 20 messages per minute
        }
        return limits.get(handler_name, (self.throttling_default_max, self.throttling_default_per_seconds))
```

## Step 2: Custom Middleware

Create custom middleware that extends Sentinel:

```python
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Any
import logging

class CustomProtectionMiddleware(BaseMiddleware):
    """Custom protection middleware with additional features."""
    
    def __init__(self, sentinel: Sentinel):
        self.sentinel = sentinel
        self.logger = logging.getLogger(__name__)
    
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Any],
        event: Message | CallbackQuery,
        data: dict[str, Any]
    ) -> Any:
        """Process event with custom protection logic."""
        
        # Log all events
        self.logger.info(f"Processing event: {type(event).__name__}")
        
        # Custom protection for specific users
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id
            
            # VIP users get higher rate limits
            if user_id in [12345, 67890]:  # Replace with actual VIP user IDs
                data["custom_rate_limit"] = (50, 60)  # 50 messages per minute
            
            # Block users from specific countries (example)
            if hasattr(event.from_user, 'language_code'):
                if event.from_user.language_code in ['ru', 'zh']:  # Example blocking
                    self.logger.warning(f"Blocked user {user_id} from restricted region")
                    return
        
        # Call the original handler
        return await handler(event, data)
```

## Step 3: Handler-Specific Configuration

Configure different protection levels for different handlers:

```python
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram_sentinel import Sentinel, SentinelConfig

# Custom configuration
config = SentinelConfig(
    throttling_default_max=5,
    throttling_default_per_seconds=60,
)

sentinel = Sentinel(config=config)

# Register middleware
dp.message.middleware(sentinel.middleware)

@dp.message(Command("start"))
async def start_command(message: Message):
    """Start command with custom rate limiting."""
    # This handler will use default rate limiting
    await message.answer("Welcome! Use /help for commands.")

@dp.message(Command("help"))
async def help_command(message: Message):
    """Help command with custom rate limiting."""
    # This handler will use default rate limiting
    await message.answer("Available commands: /start, /help, /status")

@dp.message(Command("admin"))
async def admin_command(message: Message):
    """Admin command with higher rate limits."""
    # Set custom rate limit for this handler
    message.sentinel_rate_limit = {"limit": 20, "window": 60}
    await message.answer("Admin panel access granted.")
```

## Step 4: Dynamic Configuration

Create configuration that changes based on conditions:

```python
import time
from aiogram_sentinel import SentinelConfig

class DynamicConfig(SentinelConfig):
    """Configuration that changes based on conditions."""
    
    def __init__(self):
        super().__init__()
        self._peak_hours = (9, 17)  # 9 AM to 5 PM
    
    def get_current_rate_limit(self) -> tuple[int, int]:
        """Get rate limit based on current time."""
        current_hour = time.localtime().tm_hour
        
        if self._peak_hours[0] <= current_hour <= self._peak_hours[1]:
            # Peak hours: stricter limits
            return (3, 60)
        else:
            # Off-peak hours: more lenient
            return (10, 60)
    
    def get_debounce_window(self) -> int:
        """Get debounce window based on current load."""
        # This could be based on Redis metrics, system load, etc.
        return 2  # 2 seconds
```

## Step 5: Environment-Based Configuration

Use environment variables for different environments:

```python
import os
from aiogram_sentinel import SentinelConfig

def create_config_from_env() -> SentinelConfig:
    """Create configuration from environment variables."""
    
    return SentinelConfig(
        # Rate limiting
        throttling_default_max=int(os.getenv("THROTTLING_MAX", "5")),
        throttling_default_per_seconds=int(os.getenv("THROTTLING_WINDOW", "60")),
        
        # Debounce
        debounce_default_window=int(os.getenv("DEBOUNCE_WINDOW", "3")),
        
        # Blocklist
        blocklist_enabled=os.getenv("BLOCKLIST_ENABLED", "true").lower() == "true",
        
        # Authentication
        auth_required=os.getenv("AUTH_REQUIRED", "false").lower() == "true",
    )

# Usage
config = create_config_from_env()
sentinel = Sentinel(config=config)
```

## Step 6: Configuration Validation

Add validation to your configuration:

```python
from aiogram_sentinel import SentinelConfig
from aiogram_sentinel.exceptions import ConfigurationError

class ValidatedConfig(SentinelConfig):
    """Configuration with validation."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._validate()
    
    def _validate(self):
        """Validate configuration parameters."""
        if self.throttling_default_max <= 0:
            raise ConfigurationError("throttling_default_max must be positive")
        
        if self.throttling_default_per_seconds <= 0:
            raise ConfigurationError("throttling_default_per_seconds must be positive")
        
        if self.debounce_default_window < 0:
            raise ConfigurationError("debounce_default_window must be non-negative")
        
        if self.throttling_default_max > 1000:
            raise ConfigurationError("throttling_default_max too high (max 1000)")
```

## Step 7: Configuration Hot Reloading

Implement configuration that can be reloaded without restart:

```python
import json
import asyncio
from pathlib import Path
from aiogram_sentinel import SentinelConfig

class HotReloadConfig(SentinelConfig):
    """Configuration that can be reloaded from file."""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = Path(config_file)
        self._load_config()
        super().__init__(**self._config_data)
    
    def _load_config(self):
        """Load configuration from file."""
        if self.config_file.exists():
            with open(self.config_file) as f:
                self._config_data = json.load(f)
        else:
            self._config_data = {}
    
    async def reload(self):
        """Reload configuration from file."""
        self._load_config()
        # Update instance attributes
        for key, value in self._config_data.items():
            setattr(self, key, value)
    
    def save(self):
        """Save current configuration to file."""
        config_data = {
            "throttling_default_max": self.throttling_default_max,
            "throttling_default_per_seconds": self.throttling_default_per_seconds,
            "debounce_default_window": self.debounce_default_window,
            "blocklist_enabled": self.blocklist_enabled,
            "auth_required": self.auth_required,
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
```

## Step 8: Complete Example

Put it all together:

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram_sentinel import Sentinel
from aiogram_sentinel.storage import RedisStorage

# Set up logging
logging.basicConfig(level=logging.INFO)

# Create bot and dispatcher
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# Create advanced configuration
config = HotReloadConfig("bot_config.json")

# Create Redis storage
redis_storage = RedisStorage("redis://localhost:6379")

# Create Sentinel with advanced configuration
sentinel = Sentinel(config=config, storage=redis_storage)

# Register middleware
dp.message.middleware(sentinel.middleware)

@dp.message(Command("reload_config"))
async def reload_config(message: Message):
    """Reload configuration without restart."""
    try:
        await config.reload()
        await message.answer("✅ Configuration reloaded successfully")
    except Exception as e:
        await message.answer(f"❌ Failed to reload configuration: {e}")

@dp.message(Command("save_config"))
async def save_config(message: Message):
    """Save current configuration to file."""
    try:
        config.save()
        await message.answer("✅ Configuration saved successfully")
    except Exception as e:
        await message.answer(f"❌ Failed to save configuration: {e}")

@dp.message()
async def handle_message(message: Message):
    """Handle all messages with advanced protection."""
    await message.answer(f"Hello! Your message: {message.text}")

async def main():
    """Start the bot."""
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Verify Results

Your advanced configuration should:
- ✅ Support custom rate limits per handler
- ✅ Handle environment-based configuration
- ✅ Validate configuration parameters
- ✅ Support hot reloading
- ✅ Persist configuration to file

## What's Next?

- [Custom Middleware Tutorial](custom-middleware.md)
- [Performance Optimization Tutorial](performance-optimization.md)
- [API Reference](../api/)

## Troubleshooting

**Configuration errors**: Check validation messages and parameter ranges.

**Hot reload issues**: Ensure file permissions and JSON format.

**Environment variables**: Verify variable names and types.

**Performance issues**: Monitor configuration complexity and reload frequency.
