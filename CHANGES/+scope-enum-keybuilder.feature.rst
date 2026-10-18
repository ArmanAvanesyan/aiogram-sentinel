Add Scope enum and composite KeyBuilder for unified, collision-proof key generation across all modules with support for user/chat/group/global scopes.

**New Features:**

* **Scope Enum**: Added `Scope` enum with `USER`, `CHAT`, `GROUP`, and `GLOBAL` values for defining key scoping levels
* **KeyParts Dataclass**: Added `KeyParts` dataclass for structuring key components (namespace, scope, identifiers)
* **KeyBuilder Class**: Added `KeyBuilder` class for constructing canonical keys with stable ordering and collision-proof scheme
* **Context Extractors**: Added utility functions for extracting user/chat IDs and event information from aiogram events
* **Unified Key Format**: Implemented canonical key format: `<app>:<namespace>:<scope>:<id1>[:<id2>]:[m=<method>]:[b=<bucket>]`

**API Changes:**

* **Public API**: Added `Scope`, `KeyParts`, and `KeyBuilder` to public API exports
* **Middleware Updates**: Updated `ThrottlingMiddleware` and `DebounceMiddleware` to use new KeyBuilder system
* **Sentinel Integration**: Wired KeyBuilder into `Sentinel` class initialization
* **Deprecation**: Marked `rate_key()` and `debounce_key()` functions as deprecated (removal planned for v2.0.0)

**Key Benefits:**

* **Collision-Proof**: Keys are guaranteed to be unique across different inputs
* **Stable Format**: Consistent key format across memory and Redis backends
* **Automatic Scope Selection**: Middleware automatically selects appropriate scope based on available context
* **Backward Compatible**: Deprecated functions continue to work with deprecation warnings
* **Extensible**: Easy to add new namespaces and scopes for future features

**Migration Guide:**

* Replace `rate_key(user_id, handler_name, **kwargs)` with `KeyBuilder(app).user("throttle", user_id, bucket=handler_name, **kwargs)`
* Replace `debounce_key(user_id, handler_name, **kwargs)` with `KeyBuilder(app).user("debounce", user_id, bucket=handler_name, **kwargs)`
* Use context extractors for consistent user/chat ID extraction across modules

**Documentation:**

* Added comprehensive API reference in `docs/api/keys-scopes.md`
* Updated core API documentation with new classes and functions
* Added troubleshooting section for key generation issues
* Included migration examples and best practices

**Testing:**

* Added comprehensive test suite with 100+ test cases covering all edge cases
* Property-based tests ensuring key uniqueness and format consistency
* Integration tests verifying middleware behavior with new key system
* Backward compatibility tests ensuring deprecated functions produce identical output
