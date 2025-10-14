Policy Registry + @sentinel.policy(...) Decorator

**New Features:**

* **Policy Registry**: Centralized policy definitions with `PolicyRegistry` class for managing named policies
* **Policy Configuration Classes**: `ThrottleCfg` and `DebounceCfg` dataclasses for structured policy configuration
* **@policy() Decorator**: Declarative policy attachment to handlers with support for multiple policies
* **Scope Cap Logic**: Policy scope constraints that act as maximum limits, preventing over-throttling
* **Policy Resolution Middleware**: `PolicyResolverMiddleware` that runs first in the middleware chain
* **Legacy Compatibility**: Full backward compatibility with existing `@rate_limit` and `@debounce` decorators
* **Error Handling**: Comprehensive error handling with "did you mean" suggestions for missing policies

**API Changes:**

* **New Public API**: Added `Policy`, `PolicyRegistry`, `PolicyKind`, `ThrottleCfg`, `DebounceCfg`, `policy`, `registry`, `coerce_scope`, `resolve_scope` to public exports
* **Scope Enum Update**: Changed `Scope` enum to use string values (`USER = "user"`, etc.) for better serialization
* **Middleware Order**: `PolicyResolverMiddleware` now runs first in the middleware chain before debouncing and throttling
* **Deprecation**: Marked `@rate_limit` and `@debounce` decorators as deprecated (removal planned for v2.0.0)

**Key Benefits:**

* **Define Once, Reuse Everywhere**: Policies can be defined once and reused across multiple handlers
* **Centralized Management**: All policy definitions in one place for easier maintenance
* **Composition Support**: Multiple policies can be composed on a single handler
* **Scope Safety**: Scope cap logic prevents accidental over-throttling
* **Better Error Messages**: Clear error messages with suggestions for missing policies
* **Backward Compatible**: Existing code continues to work with deprecation warnings

**Migration Guide:**

* Replace `@rate_limit(5, 60, scope="user")` with policy registry approach:
  ```python
  from aiogram_sentinel import registry, policy, Policy, ThrottleCfg, Scope
  
  registry.register(Policy("user_throttle", "throttle", ThrottleCfg(rate=5, per=60, scope=Scope.USER)))
  
  @policy("user_throttle")
  async def handler(message): ...
  ```
* Replace `@debounce(2, scope="chat")` with policy registry approach:
  ```python
  registry.register(Policy("chat_debounce", "debounce", DebounceCfg(window=2, scope=Scope.CHAT)))
  
  @policy("chat_debounce")
  async def handler(message): ...
  ```
* Use `Scope` enum instead of string values for better type safety
* Multiple policies can be attached: `@policy("policy1", "policy2")`

**Technical Details:**

* **Policy Resolution**: Policies are resolved in order, with later policies overriding earlier ones for the same kind
* **Scope Resolution**: `resolve_scope()` picks the most specific available scope within the cap constraint
* **Error Handling**: Missing policies raise `ValueError` with `difflib.get_close_matches()` suggestions
* **Legacy Support**: Legacy decorators are converted to policy configurations with deprecation warnings
* **Middleware Integration**: Policy configurations are injected into middleware data for consumption by throttling and debouncing middlewares
