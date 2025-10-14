# Keys & Scopes API Reference

This document describes the unified key generation system introduced in aiogram-sentinel v1.1.0, which provides collision-proof key generation across all modules.

## Overview

The new key system consists of three main components:

- **Scope**: An enum defining different levels of key scoping
- **KeyParts**: A dataclass for structuring key components
- **KeyBuilder**: A class for constructing canonical keys

## Scope Enum

The `Scope` enum defines four levels of key scoping:

```python
from aiogram_sentinel import Scope

# Available scopes
Scope.USER    # User-specific keys
Scope.CHAT    # Chat-specific keys  
Scope.GROUP   # User+chat composite keys
Scope.GLOBAL  # Global keys (no user/chat context)
```

### Scope Usage Guidelines

- **USER**: Use when you have a user ID but no chat context (e.g., private messages)
- **CHAT**: Use when you have a chat ID but no user context (e.g., anonymous events)
- **GROUP**: Use when you have both user and chat IDs (e.g., group messages)
- **GLOBAL**: Use when you have neither user nor chat context (e.g., system events)

## KeyParts Dataclass

The `KeyParts` dataclass structures the components of a key:

```python
from aiogram_sentinel import KeyParts, Scope

# Create key parts
parts = KeyParts(
    namespace="throttle",           # Key namespace (e.g., "throttle", "debounce")
    scope=Scope.USER,              # Scope level
    identifiers=("12345",)         # Tuple of identifier strings
)

# For GROUP scope with multiple identifiers
parts = KeyParts(
    namespace="throttle",
    scope=Scope.GROUP,
    identifiers=("12345", "67890")  # user_id, chat_id
)
```

### KeyParts Validation

- `namespace` cannot be empty
- `identifiers` cannot be empty
- Individual identifiers cannot be empty
- Identifiers cannot contain the separator character (`:`)

## KeyBuilder Class

The `KeyBuilder` class constructs canonical keys with stable ordering:

```python
from aiogram_sentinel import KeyBuilder

# Initialize with app prefix
kb = KeyBuilder(app="sentinel")

# Build key using KeyParts
key = kb.for_update(parts, method="sendMessage", bucket="handler_name")
```

### Key Format

Keys follow this canonical format:

```
<app>:<namespace>:<scope>:<id1>[:<id2>]:[m=<method>]:[b=<bucket>]
```

Examples:
```
sentinel:throttle:USER:12345
sentinel:throttle:GROUP:12345:67890:m=sendMessage
sentinel:debounce:CHAT:67890:b=handler_name
sentinel:retryafter:GLOBAL
```

### Convenience Methods

KeyBuilder provides convenience methods for each scope:

```python
# User scope
key = kb.user("throttle", user_id=12345, method="sendMessage")

# Chat scope  
key = kb.chat("throttle", chat_id=67890, bucket="handler")

# Group scope
key = kb.group("throttle", user_id=12345, chat_id=67890)

# Global scope
key = kb.global_("throttle", method="sendMessage")
```

## Context Extractors

Context extractors are utility functions for extracting user and chat information from aiogram events:

```python
from aiogram_sentinel.context import (
    extract_user_id,
    extract_chat_id, 
    extract_group_ids,
    extract_event_type,
    extract_handler_bucket,
    extract_callback_bucket
)

# Extract user ID from event
user_id = extract_user_id(event, data)

# Extract chat ID from event
chat_id = extract_chat_id(event, data)

# Extract both user and chat IDs
user_id, chat_id = extract_group_ids(event, data)

# Extract event type
event_type = extract_event_type(event, data)

# Extract handler bucket
bucket = extract_handler_bucket(event, data)

# Extract callback bucket
bucket = extract_callback_bucket(event, data)
```

### Context Extractor Behavior

- **extract_user_id**: Returns user ID from `from_user`, `user`, or chat (for private chats)
- **extract_chat_id**: Returns chat ID from `chat` or `message.chat`
- **extract_group_ids**: Returns tuple of (user_id, chat_id)
- **extract_event_type**: Returns lowercase event type name
- **extract_handler_bucket**: Returns handler name from data or event
- **extract_callback_bucket**: Parses callback data to extract action

## Migration Guide

### From Deprecated Functions

The old `rate_key()` and `debounce_key()` functions are deprecated:

```python
# Old (deprecated)
from aiogram_sentinel.utils.keys import rate_key, debounce_key

key = rate_key(user_id, handler_name, **kwargs)
key = debounce_key(user_id, handler_name, **kwargs)
```

```python
# New (recommended)
from aiogram_sentinel import KeyBuilder

kb = KeyBuilder(app="sentinel")
key = kb.user("throttle", user_id, bucket=handler_name, **kwargs)
key = kb.user("debounce", user_id, bucket=handler_name, **kwargs)
```

### Scope Selection Logic

The middleware automatically selects the appropriate scope:

```python
# Automatic scope selection
if user_id and chat_id:
    # Use GROUP scope
    key = kb.group("throttle", user_id, chat_id, **kwargs)
elif user_id:
    # Use USER scope  
    key = kb.user("throttle", user_id, **kwargs)
elif chat_id:
    # Use CHAT scope
    key = kb.chat("throttle", chat_id, **kwargs)
else:
    # Use GLOBAL scope
    key = kb.global_("throttle", **kwargs)
```

### Custom Key Generation

For custom key generation, use KeyBuilder directly:

```python
from aiogram_sentinel import KeyBuilder, KeyParts, Scope

kb = KeyBuilder(app="myapp")

# Custom namespace
parts = KeyParts(
    namespace="custom",
    scope=Scope.USER,
    identifiers=(str(user_id),)
)

key = kb.for_update(parts, method="customMethod", bucket="customBucket")
```

## Best Practices

### Key Naming

- Use descriptive namespaces: `"throttle"`, `"debounce"`, `"retryafter"`
- Use meaningful method names: `"sendMessage"`, `"editMessage"`, `"deleteMessage"`
- Use handler names as buckets: `"message_handler"`, `"callback_handler"`

### Scope Selection

- Prefer GROUP scope when both user and chat are available
- Use USER scope for user-specific operations
- Use CHAT scope for chat-specific operations  
- Use GLOBAL scope for system-wide operations

### Error Handling

KeyBuilder validates inputs and raises `ValueError` for invalid data:

```python
try:
    key = kb.user("throttle", user_id, method="invalid:method")
except ValueError as e:
    # Handle validation error
    print(f"Invalid key parameters: {e}")
```

## Examples

### Basic Usage

```python
from aiogram_sentinel import KeyBuilder, Scope, KeyParts

# Initialize KeyBuilder
kb = KeyBuilder(app="mybot")

# Simple user key
key = kb.user("throttle", 12345)
# Result: "mybot:throttle:USER:12345"

# Key with method and bucket
key = kb.user("throttle", 12345, method="sendMessage", bucket="handler")
# Result: "mybot:throttle:USER:12345:m=sendMessage:b=handler"

# Group key
key = kb.group("debounce", 12345, 67890)
# Result: "mybot:debounce:GROUP:12345:67890"
```

### Advanced Usage

```python
# Custom KeyParts
parts = KeyParts(
    namespace="custom",
    scope=Scope.GROUP,
    identifiers=("12345", "67890")
)

key = kb.for_update(parts, method="customMethod", bucket="customBucket")
# Result: "mybot:custom:GROUP:12345:67890:m=customMethod:b=customBucket"
```

### Middleware Integration

```python
from aiogram_sentinel import Sentinel, SentinelConfig

# Configure Sentinel
config = SentinelConfig(redis_prefix="mybot")

# Sentinel automatically creates KeyBuilder and passes it to middlewares
router, infra = await Sentinel.setup(dp, config)
```

## Troubleshooting

### Common Issues

1. **Key validation errors**: Ensure identifiers don't contain separator characters
2. **Scope selection**: Check that user_id and chat_id are properly extracted
3. **Deprecation warnings**: Update code to use KeyBuilder instead of deprecated functions

### Debugging Keys

```python
# Enable debug logging to see generated keys
import logging
logging.getLogger("aiogram_sentinel").setLevel(logging.DEBUG)

# Print generated keys
print(f"Generated key: {key}")
```

### Key Collision Detection

Keys are designed to be collision-proof, but you can verify uniqueness:

```python
# Test key uniqueness
keys = set()
for user_id in range(1000):
    key = kb.user("throttle", user_id)
    assert key not in keys, f"Key collision: {key}"
    keys.add(key)
```
