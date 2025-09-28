# ADR-0003: Configuration System Design

**Status**: Accepted  
**Date**: 2024-09-28  
**Authors**: ArmanAvanesyan  

## Context

aiogram-sentinel needs a flexible configuration system that supports:
- Global defaults for all protection features
- Per-handler overrides for specific use cases
- Environment-based configuration for different deployments
- Type safety and validation
- Easy integration with existing aiogram applications

The configuration system must balance simplicity for basic use cases with flexibility for advanced scenarios.

## Decision

We will implement a multi-layered configuration system with the following components:

**Core Configuration**:
- `SentinelConfig`: Central configuration class with validation
- Typed configuration parameters with sensible defaults
- Immutable configuration objects

**Configuration Sources** (in precedence order):
1. Handler-specific decorators (highest priority)
2. Runtime configuration updates
3. Code-based configuration
4. Environment variables
5. Configuration files
6. Default values (lowest priority)

**Override Mechanisms**:
- Decorators for handler-specific settings
- Handler attributes for dynamic configuration
- Runtime configuration updates

## Alternatives Considered

### 1. Environment Variables Only

**Pros**: Simple, follows 12-factor app principles
**Cons**: Limited type safety, verbose for complex configs, no per-handler overrides

**Rejected**: Too limiting for per-handler configuration needs

### 2. Configuration Files Only

**Pros**: Centralized, version controlled, supports complex structures
**Cons**: Additional file management, harder for simple cases, deployment complexity

**Rejected**: Adds unnecessary complexity for simple use cases

### 3. Mutable Global Configuration

**Pros**: Can be changed at runtime, single source of truth
**Cons**: Thread safety issues, hard to reason about, testing complications

**Rejected**: Creates too many concurrency and testing issues

### 4. Dependency Injection Container

**Pros**: Very flexible, testable, follows enterprise patterns
**Cons**: Over-engineered for this use case, steep learning curve

**Rejected**: Too complex for a middleware library

## Consequences

### Positive

- **Flexibility**: Supports simple and complex configuration scenarios
- **Type Safety**: Full type annotations and runtime validation
- **Testability**: Immutable configuration makes testing easier
- **Developer Experience**: Clear precedence rules, good defaults
- **Performance**: Configuration resolved once per handler call

### Negative

- **Complexity**: Multiple configuration sources to understand
- **Memory**: Per-handler configuration caching
- **Learning Curve**: Advanced features require understanding precedence

### Risks

- **Configuration Drift**: Different environments with different configs
- **Precedence Confusion**: Users may not understand override order
- **Performance**: Configuration resolution overhead

## Implementation Details

### Core Configuration Class

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class SentinelConfig:
    # Rate limiting
    throttling_default_max: int = 10
    throttling_default_per_seconds: int = 60
    
    # Debouncing
    debounce_default_window: int = 5
    
    # Blocking
    blocklist_enabled: bool = True
    
    # Authentication
    auth_required: bool = False
    
    def __post_init__(self):
        """Validate configuration parameters."""
        if self.throttling_default_max <= 0:
            raise ConfigurationError("throttling_default_max must be positive")
        
        if self.throttling_default_per_seconds <= 0:
            raise ConfigurationError("throttling_default_per_seconds must be positive")
        
        if self.debounce_default_window < 0:
            raise ConfigurationError("debounce_default_window must be non-negative")
```

### Environment Variable Support

```python
import os
from typing import Type, TypeVar

T = TypeVar('T', bound=SentinelConfig)

def load_from_env(config_class: Type[T]) -> T:
    """Load configuration from environment variables."""
    kwargs = {}
    
    # Map environment variables to config fields
    env_mapping = {
        'SENTINEL_THROTTLING_MAX': 'throttling_default_max',
        'SENTINEL_THROTTLING_WINDOW': 'throttling_default_per_seconds',
        'SENTINEL_DEBOUNCE_WINDOW': 'debounce_default_window',
        'SENTINEL_BLOCKLIST_ENABLED': 'blocklist_enabled',
        'SENTINEL_AUTH_REQUIRED': 'auth_required',
    }
    
    for env_var, field_name in env_mapping.items():
        if env_var in os.environ:
            value = os.environ[env_var]
            # Type conversion based on field type
            kwargs[field_name] = convert_env_value(value, field_name)
    
    return config_class(**kwargs)
```

### Handler-Specific Configuration

```python
from functools import wraps
from typing import Callable, Any

def sentinel_rate_limit(limit: int, window: int):
    """Decorator for handler-specific rate limiting."""
    def decorator(handler: Callable) -> Callable:
        # Store configuration on handler
        handler.sentinel_rate_limit = {"limit": limit, "window": window}
        return handler
    return decorator

def sentinel_debounce(delay: int):
    """Decorator for handler-specific debouncing."""
    def decorator(handler: Callable) -> Callable:
        handler.sentinel_debounce = {"delay": delay}
        return handler
    return decorator
```

### Configuration Resolution

```python
class ConfigResolver:
    """Resolves configuration with proper precedence."""
    
    def __init__(self, base_config: SentinelConfig):
        self.base_config = base_config
        self._cache: dict[str, Any] = {}
    
    def get_rate_limit_config(self, handler: Callable, data: dict[str, Any]) -> tuple[int, int]:
        """Get rate limit configuration for a specific handler."""
        cache_key = f"rate_limit:{handler.__name__}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 1. Check handler decorator
        if hasattr(handler, 'sentinel_rate_limit'):
            config = handler.sentinel_rate_limit
            if isinstance(config, dict):
                result = (config.get('limit'), config.get('window'))
            elif isinstance(config, (tuple, list)):
                result = (config[0], config[1])
        
        # 2. Check handler attributes (runtime)
        elif 'sentinel_rate_limit' in data:
            config = data['sentinel_rate_limit']
            result = (config['limit'], config['window'])
        
        # 3. Use defaults
        else:
            result = (
                self.base_config.throttling_default_max,
                self.base_config.throttling_default_per_seconds
            )
        
        self._cache[cache_key] = result
        return result
```

### Configuration File Support

```python
import json
import yaml
from pathlib import Path

def load_from_file(file_path: str) -> SentinelConfig:
    """Load configuration from file (JSON or YAML)."""
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    
    content = path.read_text()
    
    if path.suffix.lower() == '.json':
        data = json.loads(content)
    elif path.suffix.lower() in ['.yml', '.yaml']:
        data = yaml.safe_load(content)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")
    
    return SentinelConfig(**data)
```

## Configuration Precedence

The configuration system resolves values in this order (highest to lowest priority):

1. **Handler Decorators**: `@sentinel_rate_limit(limit=5, window=60)`
2. **Handler Attributes**: `handler.sentinel_rate_limit = {"limit": 5, "window": 60}`
3. **Runtime Data**: `data["sentinel_rate_limit"] = {"limit": 5, "window": 60}`
4. **Code Configuration**: `SentinelConfig(throttling_default_max=5)`
5. **Environment Variables**: `SENTINEL_THROTTLING_MAX=5`
6. **Configuration Files**: `config.json` or `config.yaml`
7. **Default Values**: Built-in defaults in `SentinelConfig`

## Example Usage Patterns

### Simple Configuration

```python
# Use defaults
sentinel = Sentinel()

# Basic customization
config = SentinelConfig(throttling_default_max=5)
sentinel = Sentinel(config=config)
```

### Environment-Based Configuration

```python
# Production
config = load_from_env(SentinelConfig)
sentinel = Sentinel(config=config)

# With file fallback
try:
    config = load_from_file("config.prod.yaml")
except FileNotFoundError:
    config = load_from_env(SentinelConfig)
```

### Handler-Specific Configuration

```python
@dp.message(Command("start"))
@sentinel_rate_limit(limit=3, window=60)  # 3 messages per minute
async def start_handler(message: Message):
    await message.answer("Welcome!")

@dp.message(Command("admin"))
async def admin_handler(message: Message):
    # Dynamic configuration
    if message.from_user.id in ADMIN_IDS:
        message.sentinel_rate_limit = {"limit": 100, "window": 60}
    
    await message.answer("Admin panel")
```

### Runtime Configuration Updates

```python
class ConfigurableBot:
    def __init__(self):
        self.config = SentinelConfig()
        self.sentinel = Sentinel(config=self.config)
    
    async def update_rate_limits(self, new_max: int):
        """Update rate limits at runtime."""
        new_config = SentinelConfig(
            throttling_default_max=new_max,
            throttling_default_per_seconds=self.config.throttling_default_per_seconds,
            # ... other fields
        )
        
        # Create new sentinel with updated config
        self.sentinel = Sentinel(config=new_config)
        
        # Re-register middleware
        dp.message.middleware.unregister(self.sentinel.middleware)
        dp.message.middleware(self.sentinel.middleware)
```

## Validation Strategy

### Type Validation

```python
from typing import get_type_hints

def validate_config(config: SentinelConfig) -> None:
    """Validate configuration at runtime."""
    hints = get_type_hints(SentinelConfig)
    
    for field_name, expected_type in hints.items():
        value = getattr(config, field_name)
        if not isinstance(value, expected_type):
            raise ConfigurationError(
                f"{field_name} must be {expected_type.__name__}, got {type(value).__name__}"
            )
```

### Business Logic Validation

```python
def validate_business_rules(config: SentinelConfig) -> None:
    """Validate business logic constraints."""
    if config.throttling_default_max > 1000:
        raise ConfigurationError("Rate limit too high (max 1000)")
    
    if config.debounce_default_window > 300:
        raise ConfigurationError("Debounce window too long (max 5 minutes)")
    
    if config.throttling_default_per_seconds < config.debounce_default_window:
        raise ConfigurationError("Rate limit window should be longer than debounce window")
```

## Testing Strategy

### Configuration Testing

```python
def test_config_precedence():
    """Test configuration precedence rules."""
    # Default configuration
    config = SentinelConfig()
    assert config.throttling_default_max == 10
    
    # Environment override
    with patch.dict(os.environ, {'SENTINEL_THROTTLING_MAX': '5'}):
        config = load_from_env(SentinelConfig)
        assert config.throttling_default_max == 5
    
    # Handler override
    @sentinel_rate_limit(limit=3, window=60)
    async def handler(): pass
    
    resolver = ConfigResolver(config)
    limit, window = resolver.get_rate_limit_config(handler, {})
    assert limit == 3
```

### Validation Testing

```python
def test_config_validation():
    """Test configuration validation."""
    with pytest.raises(ConfigurationError):
        SentinelConfig(throttling_default_max=0)  # Invalid
    
    with pytest.raises(ConfigurationError):
        SentinelConfig(debounce_default_window=-1)  # Invalid
```

## Success Metrics

- **Usability**: 90% of use cases require no configuration
- **Flexibility**: Advanced users can customize all behaviors
- **Performance**: Configuration resolution <10µs per handler call
- **Type Safety**: 100% type coverage for configuration
- **Documentation**: Clear examples for all configuration patterns

## Future Enhancements

### Hot Reloading

```python
class HotReloadConfig(SentinelConfig):
    """Configuration that can be reloaded without restart."""
    
    @classmethod
    def from_file_with_reload(cls, file_path: str, reload_interval: int = 60):
        # Watch file for changes
        # Reload configuration automatically
        pass
```

### Configuration UI

```python
# Web-based configuration management
app = web.Application()
app.router.add_get("/config", get_current_config)
app.router.add_post("/config", update_config)
```

### Configuration Schema

```python
# JSON Schema for validation and IDE support
CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "throttling_default_max": {"type": "integer", "minimum": 1},
        "throttling_default_per_seconds": {"type": "integer", "minimum": 1},
        # ...
    }
}
```

## References

- [12-Factor App Configuration](https://12factor.net/config)
- [Python Dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [Pydantic Settings](https://pydantic-docs.helpmanual.io/usage/settings/)

## Related ADRs

- ADR-0001: Middleware Architecture
- ADR-0002: Storage Backend Architecture
- ADR-0004: Error Handling Strategy
