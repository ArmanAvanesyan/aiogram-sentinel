# Public API

All supported integration imports come from `aiogram_coordination`.

- `CoordinationKey(namespace, bot_id, chat_id, user_id, tenant_id=None)` is immutable.
  Namespaces and optional tenants contain at most 128 characters. Identifier
  numbers are positive non-Boolean integers. No identity component is dropped.
- `coordination_key(value)` converts a structural full-identity peer key. A
  partially specified or invalid identity fails instead of receiving defaults.
  Nondefault FSM thread/business/destiny dimensions require an explicit mapping,
  rather than being silently discarded by conversation normalization.
- `Coordinator` exposes `hold(key)`, `scope_token(key)`, `scope_active(token)`,
  `scope_matches(key, token)` and `active_scopes`.
- `BorrowedFsmCoordinator` is a runtime-checkable structural capability exposing
  `fsm_isolation`, `configure_fsm_isolation` and `borrowed_fsm`. Both built-in FSM
  coordinators and application bridges can implement it. Installers must still
  verify the configured isolation and current Tracked proof; protocol membership
  alone never grants ownership.
- `FencedCoordinator` adds `fencing(key, scope=None)`, returning a Redis lock
  key/owner-token pair or `None`. Explicit delegated capabilities must match both
  the live scope and the normalized conversation identity.
- `MemoryCoordinator` implements process-local locks. `RedisCoordinator` provides
  renewable, token-checked distributed ownership. A supplied Redis client is not
  closed by either coordinator.
- `AiogramMemoryCoordinator(isolation)` supports verified SimpleEventIsolation or
  TrackedEventIsolation. Workers call `hold`; dispatcher middleware calls
  `borrowed` only inside the proven FSM scope. Redis coordination supports the
  same pattern through `configure_fsm_isolation` and `borrowed_fsm`.
  Captured FSM proof participates in scope validity immediately on lease loss,
  even before cancellation is delivered. `TrackedEventIsolation.proof(key)`
  returns a lifetime receipt without granting another task lock reentry.
- `TrackedEventIsolation`, `IsolationProvider`, `LeaseHandle`,
  `RenewableRedisEventIsolation` and its `RedisIsolationProvider` alias support
  explicit application lock integration. See the isolation guide.
- `ExternalSession`, `SessionAuthority`, `SessionAuthorityUnavailable` and
  `validate_session_transition` express read-only authority. See session rules.

Typed failures are `ConfigurationError`, `OwnershipLost`, `PersistenceUnavailable`
and `SessionAuthorityUnavailable`, all deriving from `CoordinationError`.
Consumers may preserve their own error families through thin facades using the
Redis coordinator's exception-class hooks (`configuration_error`,
`ownership_lost_error`, `persistence_unavailable_error`).

A delegated scope capability does not grant a child task reentrant lock ownership.
The lifetime check is necessary before new external effects; it cannot cancel a
request already accepted by Telegram or another service.
