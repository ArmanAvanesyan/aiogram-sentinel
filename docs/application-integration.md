# Application-owned integration

Version 0.2 keeps navigation independent of Idle. The base distribution installs
aiogram and the neutral `aiogram-coordination` contracts; Redis remains optional.
Application authentication, sessions, FSM drafts and message storage remain owned
by the application.

## Prove the existing FSM lock

Construct the Dispatcher with an explicit wrapper rather than letting installation
replace event isolation:

```python
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram_coordination import TrackedEventIsolation

application_isolation = SimpleEventIsolation()
isolation = TrackedEventIsolation(application_isolation)
dispatcher = Dispatcher(events_isolation=isolation)
```

For custom isolation, pass `provider=...` implementing the shared `IsolationProvider`
contract. It must reference the exact application isolation and yield a key-bound
`LeaseHandle` whose validity changes immediately on ownership loss. Opaque
fixed-TTL lock implementations are rejected; an acquired context alone cannot
prove renewal or continued ownership. `RenewableRedisEventIsolation` provides a
reference implementation with the application's Redis client and FSM key builder.
The wrapper does not close its delegate unless `close_delegate=True` is explicit.

An application coordinator may implement the public shared `BorrowedFsmCoordinator`
protocol (`fsm_isolation`, `configure_fsm_isolation`, `borrowed_fsm` and the normal
coordinator methods). Installation verifies that it retains the exact wrapper. A
structural memory bridge is supported without subclassing a library coordinator.
Redis repositories additionally retain their own verified fenced coordinator core;
a `distributed=True` attribute alone does not prove distributed ownership.

Handlers borrow the verified held lock; workers/direct operations acquire the same
normalized lock. Both take the FSM lock before the backend's Redis fence. Keep
`FSMStrategy.USER_IN_CHAT`, preserve bot/chat/actor/field identity in encrypted FSM
storage key builders, and drain before changing configuration. Library installation
does not replace encrypted storage or discard its data. Children inheriting context
cannot bypass the actual owning task's lock. Do not suppress ownership cancellation
and continue application writes.

## Choose router position explicitly

Automatic installation remains strict and puts bindings before business routers.
For state-guarded application routing, create the public router, include it at the
chosen position, then install manually:

```python
from aiogram_nav import create_bindings_router

bindings_router = create_bindings_router(navigation)
dispatcher.include_router(feedback_state_guards)
dispatcher.include_router(bindings_router)
dispatcher.include_router(menu_fallbacks)
navigation.install(
    dispatcher,
    bindings_mode="manual",
    bindings_router=bindings_router,
)
```

The runtime still coordinates the whole handler. Manual mode never reorders these
routers. Intentional Dispatcher-root handlers additionally require
`allow_root_handlers=True` in manual mode. The application owns their precedence;
a catch-all can prevent valid navigation from running. Unhandled reserved callbacks
are reported. Root handlers are never implicitly allowed in automatic mode.

Before manual dispatch, reserved callbacks are checked against the actual actor,
conversation, session, view and message. Invalid controls are acknowledged without
running application handlers or cleaning old messages. Valid tokens are **not**
consumed until the selected binding handler runs. Configure `callback_rejection`
with an async callable accepting `CallbackRejection` (`callback`, `bot`, `reason`)
to localize the response. Reasons are coarse `stale`, `unsupported` or `busy`; no
other user's state is disclosed. The callback owns its acknowledgement.

## Keep rendering and cleanup in MessageStore

`ApplicationPresenter(render=render_callback, cleanup=cleanup_callback)` delegates
to application helpers. Cleanup receives generation-specific previous/current
views and an `ensure_owned()` guard; call the guard immediately before each new
external effect. The callback is the only cleanup owner.

For explicit prepared rendering, omit the render callback and use:

```python
from aiogram_nav import ApplicationPresenter

# Registry destinations use an explicit renderer key such as "application".
presenter = ApplicationPresenter(cleanup=message_store.cleanup_navigation)
prepared = await nav_context.prepare_action("back", operation_id=stable_operation_id)
request = await navigation.request(prepared)
rendered = await message_store.render_navigation(request)
await nav_context.complete_render(prepared, rendered=rendered)
```

Direct callers outside protected handlers must hold `navigation.coordinator.hold(key)`
across preparation, external rendering and completion. The injected handler context
already holds that scope. The application must return the actual `RenderResult` for the prepared view and
record independent sends through the provided effect recorder where available.
Back/Cancel/Home retain the same target, history and authorization rules as the
automatic path. Completion invokes the supplied cleanup once. Business cancel
hooks must remain idempotent or expose recoverable stage evidence.

Without a render callback, automatic `go/back/home/cancel/refresh` raises before
creating a pending operation or business effect. Binding handlers use automatic
actions, so either supply a render callback or use application handlers for the
prepared path. Abstract registry nodes still cannot be destinations.

`track()` adopts an already-rendered screen. A crash after sending and before
tracking cannot be recovered from a record that was never created; use prepared
rendering for recoverable delivery.

## Read application sessions without owning them

Pass `session_authority=` implementing the shared `SessionAuthority.current(key)`.
It returns `ExternalSession(session_id, revision, absolute_expires_at,
idle_expires_at=None)` with UTC epoch milliseconds, or `None` for no authorized
session. Availability failures raise `SessionAuthorityUnavailable`, never `None`.
The application must never reuse IDs or extend absolute expiry under one ID.

Activate storage format 2 explicitly before enabling this mode; see
[migration](migration.md). The library binds internal random generations to the
external session. It never opens, extends, replaces or clears application sessions.
Source inactivity expiry is checked live; internal absolute expiry does not slide.
Replacement invalidates current UI/controls while retaining old receipts. Unresolved
effects block rebinding until explicitly resolved; no recovery evidence is evicted.
Authority failures preserve current storage and reject new effects.

The combined Idle integration supplies one authority boundary and one atomic
navigation/activity transaction. Do not independently install both runtimes or
use two unrelated stores and describe their writes as atomic.

## Shutdown

Stop application update admission, stop Idle workers if installed, then await
`navigation.drain(timeout_seconds=10)`, close repositories, close FSM storage and
finally close application-owned Redis/Bot clients. `close()` drains before closing
owned repository resources; caller-owned clients remain open. A drain timeout
raises and never releases another task's lock or marks unfinished effects successful.
Persisted uncertainty remains recoverable after restart. Memory state does not.
