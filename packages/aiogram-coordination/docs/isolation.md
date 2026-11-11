# Application-owned FSM isolation

Construct the application isolation, wrap it explicitly, then pass the wrapper
to `Dispatcher(events_isolation=...)`. Library installers must not replace the
configured isolation after FSM middleware begins loading state.

`TrackedEventIsolation` verifies the exact application instance, full FSM
`StorageKey`, current task and live lease. `owns(key)` is task-scoped.
`borrowed(key)` refuses absent, expired, foreign or child-task ownership. Nested
calls in the actual owning task do not recursively acquire the underlying lock.

## Custom provider

Implement the public `IsolationProvider` protocol:

```python
class ApplicationProvider:
    def __init__(self, application_isolation):
        self.isolation = application_isolation

    def acquire(self, key):
        # Return an async context manager that acquires THIS application's lock.
        # It yields a LeaseHandle and always releases its own ownership.
        return self.isolation.acquire_with_receipt(key)
```

The application-owned `acquire_with_receipt` is an example of an application API,
not a method supplied by aiogram. A returned `LeaseHandle` exposes `key`, `valid`,
`assert_owned()` and `await wait_lost()`. Its identity must equal the requested
StorageKey. `valid` and `assert_owned` must account for actual ownership and expiry;
`wait_lost` signals revocation, including inability to monitor the lock.
The wrapper cancels the owner on loss and refuses success even if cancellation
is suppressed. Applications must not suppress cancellation and continue writes.

Opaque `BaseEventIsolation.lock()` alone does not expose enough evidence for
custom distributed leases and is rejected. Provider configuration and key builders must remain unchanged while in use.
The library does not invent renewal
for existing RedisEventIsolation locks whose tokens are hidden.

## Redis reference provider

`RenewableRedisEventIsolation(redis=existing_client, key_builder=builder)` is a
complete explicit application isolation provider. It uses token-checked renewal,
a fixed maximum I/O budget and the public key builder's `lock` key. It does not
wrap or invoke opaque locks, and it never closes the caller's client. Its default
builder separates bot, business connection and destiny. A supplied builder must
at least separate bot/chat/actor. The provider probes thread/business/destiny
separation too. A supplied private-only builder remains usable for default FSM
keys, but a requested unsupported dimension is rejected before any Redis command.
Two distinct nondefault values are checked so presence-only encoders cannot
silently alias all business sessions or destinies.

The actual full StorageKey remains part of scope identity. Conversation
normalization never collapses thread, destiny or business fields of FSM locks.

## Ordering, storage fencing and shutdown

Application coordinator bridges implement the public `BorrowedFsmCoordinator`
capability so installers do not need concrete package-class checks. The bridge
must borrow the live Tracked receipt and preserve scope validity; advertising
method names or `distributed=True` alone does not prove safe ownership.

Acquire application FSM isolation first, then the library's storage coordinator.
An incoming handler borrows its already-held FSM scope; a worker acquires that
same lock before storage coordination. Storage mutations still require an atomic
Redis fence check; sharing the FSM lock does not replace CAS or token validation.

Active-scope reporting includes queued acquisitions and release tails after effect
authority is already revoked. Coordinators bound to a Tracked wrapper also count
that wrapper's active application scopes, conservatively delaying drain until
external FSM release finishes.

Stop accepting updates, stop workers, drain protected scopes, then close FSM
storage and caller-owned Redis clients. `TrackedEventIsolation.close()` rejects
active scopes and does not close the delegate by default. Set
`close_delegate=True` only when that ownership is intentional. It never closes a
client independently of the configured delegate. No cross-database transaction
or exactly-once business effect is promised.
