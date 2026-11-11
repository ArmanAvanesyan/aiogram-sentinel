# Policy Patterns Tutorial

This tutorial demonstrates common patterns for using the Policy Registry to organize and reuse rate limiting and debouncing configurations.

## Common Policy Library

Create a library of reusable policies for different scenarios:

```python
from aiogram_sentinel import registry, Policy, ThrottleCfg, DebounceCfg, Scope

# User-focused policies
registry.register(Policy(
    "user_throttle", "throttle",
    ThrottleCfg(rate=5, per=60, scope=Scope.USER),
    "Standard user rate limiting"
))

registry.register(Policy(
    "user_debounce", "debounce", 
    DebounceCfg(window=2, scope=Scope.USER),
    "Prevent duplicate user actions"
))

# Chat-focused policies
registry.register(Policy(
    "chat_throttle", "throttle",
    ThrottleCfg(rate=10, per=60, scope=Scope.CHAT),
    "Chat-wide rate limiting"
))

registry.register(Policy(
    "chat_debounce", "debounce",
    DebounceCfg(window=1, scope=Scope.CHAT),
    "Prevent spam in chat"
))

# Group-specific policies
registry.register(Policy(
    "group_throttle", "throttle",
    ThrottleCfg(rate=3, per=60, scope=Scope.GROUP),
    "Strict group rate limiting"
))

# Global policies
registry.register(Policy(
    "global_throttle", "throttle",
    ThrottleCfg(rate=100, per=60, scope=Scope.GLOBAL),
    "Global rate limiting"
))
```

## "Define Once, Reuse Everywhere" Pattern

Define policies once and reuse them across multiple handlers:

```python
from aiogram_sentinel import policy

# Message handlers
@policy("user_throttle", "user_debounce")
async def handle_text_message(message):
    await message.answer("Text received!")

@policy("user_throttle", "user_debounce")
async def handle_photo_message(message):
    await message.answer("Photo received!")

# Callback handlers
@policy("user_throttle")
async def handle_button_click(callback):
    await callback.answer("Button clicked!")

# Admin handlers (more restrictive)
@policy("group_throttle")
async def handle_admin_command(message):
    await message.answer("Admin command executed!")
```

## Composing Multiple Policies

Combine different types of policies on a single handler:

```python
# Combine throttling and debouncing
@policy("user_throttle", "user_debounce")
async def handle_user_action(message):
    await message.answer("Action processed!")

# Multiple throttling policies (last wins)
@policy("user_throttle", "chat_throttle")
async def handle_chat_message(message):
    # chat_throttle will override user_throttle
    await message.answer("Message processed!")

# Mix throttling and debouncing with different scopes
@policy("user_throttle", "chat_debounce")
async def handle_mixed_action(message):
    # User-level throttling + chat-level debouncing
    await message.answer("Mixed action processed!")
```

## Scope-Specific Policies

Create policies with specific scope constraints:

```python
# DM-only policy (USER scope cap)
registry.register(Policy(
    "dm_only", "throttle",
    ThrottleCfg(rate=10, per=60, scope=Scope.USER),
    "Rate limiting for direct messages only"
))

# Group-only policy (GROUP scope cap)
registry.register(Policy(
    "group_only", "throttle", 
    ThrottleCfg(rate=5, per=60, scope=Scope.GROUP),
    "Rate limiting for group interactions only"
))

# Chat-wide policy (CHAT scope cap)
registry.register(Policy(
    "chat_wide", "debounce",
    DebounceCfg(window=3, scope=Scope.CHAT),
    "Chat-wide debouncing"
))

# Usage
@policy("dm_only")
async def handle_dm(message):
    # Only applies in direct messages
    await message.answer("DM processed!")

@policy("group_only") 
async def handle_group_action(message):
    # Only applies in group chats
    await message.answer("Group action processed!")
```

## Method and Bucket Organization

Use method and bucket parameters for fine-grained control:

```python
# Method-specific policies
registry.register(Policy(
    "send_message_throttle", "throttle",
    ThrottleCfg(rate=5, per=60, method="sendMessage"),
    "Throttle sendMessage API calls"
))

registry.register(Policy(
    "edit_message_throttle", "throttle", 
    ThrottleCfg(rate=10, per=60, method="editMessageText"),
    "Throttle editMessageText API calls"
))

# Bucket-specific policies
registry.register(Policy(
    "callback_throttle", "throttle",
    ThrottleCfg(rate=3, per=60, bucket="callbacks"),
    "Throttle callback queries"
))

registry.register(Policy(
    "inline_throttle", "throttle",
    ThrottleCfg(rate=20, per=60, bucket="inline"),
    "Throttle inline queries"
))

# Usage
@policy("send_message_throttle")
async def send_message_handler(message):
    await message.answer("Message sent!")

@policy("callback_throttle")
async def callback_handler(callback):
    await callback.answer("Callback processed!")
```

## Testing with Policies

Test handlers with different policy configurations:

```python
import pytest
from aiogram_sentinel import registry, Policy, ThrottleCfg, DebounceCfg, Scope

@pytest.fixture
def test_policies():
    """Set up test policies."""
    registry.clear()
    
    registry.register(Policy(
        "test_throttle", "throttle",
        ThrottleCfg(rate=2, per=60, scope=Scope.USER)
    ))
    
    registry.register(Policy(
        "test_debounce", "debounce",
        DebounceCfg(window=1, scope=Scope.USER)
    ))

def test_handler_with_policies(test_policies):
    """Test handler with policies."""
    from aiogram_sentinel import policy
    
    @policy("test_throttle", "test_debounce")
    async def test_handler():
        return "test"
    
    # Verify policies are attached
    assert hasattr(test_handler, "__sentinel_policies__")
    assert test_handler.__sentinel_policies__ == ("test_throttle", "test_debounce")
    
    # Test policy resolution
    from aiogram_sentinel.middlewares.policy_resolver import PolicyResolverMiddleware
    from aiogram_sentinel import SentinelConfig
    
    cfg = SentinelConfig()
    resolver = PolicyResolverMiddleware(registry, cfg)
    throttle_cfg, debounce_cfg = resolver._resolve_configurations(test_handler)
    
    assert throttle_cfg.rate == 2
    assert throttle_cfg.per == 60
    assert throttle_cfg.scope == Scope.USER
    
    assert debounce_cfg.window == 1
    assert debounce_cfg.scope == Scope.USER
```

## Environment-Specific Policies

Create different policy sets for different environments:

```python
import os
from aiogram_sentinel import registry, Policy, ThrottleCfg, DebounceCfg, Scope

def setup_development_policies():
    """Set up policies for development environment."""
    registry.clear()
    
    # Relaxed policies for development
    registry.register(Policy(
        "dev_throttle", "throttle",
        ThrottleCfg(rate=100, per=60, scope=Scope.USER),
        "Development throttling"
    ))
    
    registry.register(Policy(
        "dev_debounce", "debounce",
        DebounceCfg(window=0.5, scope=Scope.USER),
        "Development debouncing"
    ))

def setup_production_policies():
    """Set up policies for production environment."""
    registry.clear()
    
    # Strict policies for production
    registry.register(Policy(
        "prod_throttle", "throttle",
        ThrottleCfg(rate=5, per=60, scope=Scope.USER),
        "Production throttling"
    ))
    
    registry.register(Policy(
        "prod_debounce", "debounce",
        DebounceCfg(window=2, scope=Scope.USER),
        "Production debouncing"
    ))

# Set up policies based on environment
if os.getenv("ENVIRONMENT") == "production":
    setup_production_policies()
else:
    setup_development_policies()
```

## Policy Validation and Error Handling

Handle policy errors gracefully:

```python
from aiogram_sentinel import registry, policy
import logging

logger = logging.getLogger(__name__)

def safe_policy_attachment(policy_names):
    """Safely attach policies with error handling."""
    def decorator(handler):
        try:
            # Validate all policies exist
            for name in policy_names:
                registry.get(name)
            
            # Attach policies
            return policy(*policy_names)(handler)
            
        except ValueError as e:
            logger.error(f"Failed to attach policies {policy_names}: {e}")
            # Return handler without policies
            return handler
    
    return decorator

# Usage
@safe_policy_attachment(["user_throttle", "user_debounce"])
async def safe_handler(message):
    await message.answer("Handler executed!")

# Or handle errors in the handler itself
@policy("user_throttle", "user_debounce")
async def handler_with_error_handling(message):
    try:
        await message.answer("Handler executed!")
    except Exception as e:
        logger.error(f"Handler error: {e}")
        # Handle error appropriately
```

## Best Practices

1. **Organize by Feature**: Group related policies together
2. **Use Descriptive Names**: Make policy names self-documenting
3. **Document Policies**: Add descriptions to explain policy purpose
4. **Test Policy Resolution**: Verify policies resolve correctly
5. **Handle Errors**: Gracefully handle missing or invalid policies
6. **Environment Awareness**: Use different policies for different environments
7. **Scope Appropriately**: Choose the right scope for each policy
8. **Monitor Performance**: Track policy effectiveness and adjust as needed
