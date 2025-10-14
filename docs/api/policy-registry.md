# Policy Registry API

The Policy Registry provides centralized policy definitions with declarative attachment to handlers via the `@policy()` decorator. This enables the "define once, reuse everywhere" pattern for rate limiting and debouncing configurations.

## Core Components

### PolicyRegistry

The central registry for managing named policies.

```python
from aiogram_sentinel import PolicyRegistry, Policy, ThrottleCfg, DebounceCfg, Scope

registry = PolicyRegistry()

# Register policies
registry.register(Policy(
    "user_throttle", 
    "throttle", 
    ThrottleCfg(rate=5, per=60, scope=Scope.USER),
    "Rate limit for user actions"
))

registry.register(Policy(
    "chat_debounce", 
    "debounce", 
    DebounceCfg(window=2, scope=Scope.CHAT),
    "Debounce duplicate messages in chat"
))
```

#### Methods

- `register(policy: Policy)` - Register a new policy (raises ValueError on duplicate names)
- `get(name: str)` - Retrieve policy by name (raises ValueError with suggestions if not found)
- `all()` - Return all registered policies in registration order
- `clear()` - Remove all registered policies

### Policy

A named policy configuration.

```python
@dataclass(frozen=True)
class Policy:
    name: str                    # Unique policy name
    kind: PolicyKind            # "throttle" or "debounce"
    cfg: ThrottleCfg | DebounceCfg  # Configuration
    description: str = ""       # Optional description
```

### ThrottleCfg

Configuration for throttling policies.

```python
@dataclass(frozen=True)
class ThrottleCfg:
    rate: int                   # Maximum events per window
    per: int                    # Time window in seconds
    scope: Scope | None = None  # Scope cap (USER, CHAT, GROUP, GLOBAL)
    method: str | None = None   # Optional method name
    bucket: str | None = None   # Optional bucket identifier
```

### DebounceCfg

Configuration for debouncing policies.

```python
@dataclass(frozen=True)
class DebounceCfg:
    window: int                 # Debounce window in seconds
    scope: Scope | None = None  # Scope cap (USER, CHAT, GROUP, GLOBAL)
    method: str | None = None   # Optional method name
    bucket: str | None = None   # Optional bucket identifier
```

### Scope Enum

Scope enumeration for key generation and policy constraints.

```python
class Scope(Enum):
    USER = "user"      # Per-user scope
    CHAT = "chat"      # Per-chat scope
    GROUP = "group"    # Per-user+chat composite scope
    GLOBAL = "global"  # Global scope
```

## Policy Decorator

The `@policy()` decorator attaches policies to handlers.

```python
from aiogram_sentinel import policy

# Single policy
@policy("user_throttle")
async def handle_message(message):
    await message.answer("Hello!")

# Multiple policies
@policy("user_throttle", "user_debounce")
async def handle_callback(callback):
    await callback.answer("Processed!")
```

## Scope Cap Semantics

When a policy specifies an explicit scope (e.g., `Scope.USER`), it acts as a **maximum constraint**:

- The resolver picks the **most specific available scope** that is **not broader than** the cap
- If no scope can satisfy the cap, the policy is skipped (logged at DEBUG level)
- This prevents accidental over-throttling (e.g., turning a user cap into a global lock)

### Scope Specificity Order

`USER > CHAT > GROUP > GLOBAL` (most specific first)

### Examples

```python
# Policy with USER cap
throttle_cfg = ThrottleCfg(rate=5, per=60, scope=Scope.USER)

# Available: user_id=123, chat_id=456
# Resolved: USER (most specific within USER cap)

# Available: user_id=None, chat_id=456  
# Resolved: None (cannot satisfy USER cap)

# Policy with GROUP cap
throttle_cfg = ThrottleCfg(rate=5, per=60, scope=Scope.GROUP)

# Available: user_id=123, chat_id=456
# Resolved: USER (most specific within GROUP cap)

# Available: user_id=None, chat_id=456
# Resolved: CHAT (within GROUP cap)
```

## Migration from Legacy Decorators

### Before (Deprecated)

```python
from aiogram_sentinel import rate_limit, debounce

@rate_limit(5, 60, scope="user")
@debounce(2, scope="chat")
async def handler(message):
    await message.answer("Hello!")
```

### After (Recommended)

```python
from aiogram_sentinel import registry, policy, Policy, ThrottleCfg, DebounceCfg, Scope

# Register policies once
registry.register(Policy(
    "user_throttle", "throttle",
    ThrottleCfg(rate=5, per=60, scope=Scope.USER)
))

registry.register(Policy(
    "chat_debounce", "debounce", 
    DebounceCfg(window=2, scope=Scope.CHAT)
))

# Use policies everywhere
@policy("user_throttle", "chat_debounce")
async def handler(message):
    await message.answer("Hello!")
```

## Error Handling

### Policy Not Found

```python
# Raises ValueError with suggestions
try:
    registry.get("user_throtle")  # Typo
except ValueError as e:
    print(e)  # "Policy 'user_throtle' not found. Did you mean: user_throttle"
```

### Scope Cap Violation

When a policy's scope cap cannot be satisfied, the policy is skipped and logged at DEBUG level:

```python
# Policy with USER cap but no user_id available
# Logs: "Policy skipped: required scope identifiers missing"
# Continues processing without throttling/debouncing
```

## Global Registry

A global registry instance is available for convenience:

```python
from aiogram_sentinel import registry

# Use the global registry
registry.register(Policy("global_policy", "throttle", ThrottleCfg(rate=10, per=60)))
```

## Utility Functions

### coerce_scope

Convert string scope to Scope enum with deprecation warning.

```python
from aiogram_sentinel import coerce_scope, Scope

scope = coerce_scope("user")  # Returns Scope.USER, emits DeprecationWarning
scope = coerce_scope(Scope.USER)  # Returns Scope.USER, no warning
scope = coerce_scope(None)  # Returns None
```

### resolve_scope

Resolve scope with cap constraint.

```python
from aiogram_sentinel import resolve_scope, Scope

# No cap - picks most specific available
scope = resolve_scope(user_id=123, chat_id=456, cap=None)
# Returns Scope.USER

# With cap - picks most specific within cap
scope = resolve_scope(user_id=123, chat_id=456, cap=Scope.CHAT)
# Returns Scope.USER (more specific than CHAT)

# Cannot satisfy cap
scope = resolve_scope(user_id=None, chat_id=456, cap=Scope.USER)
# Returns None
```
