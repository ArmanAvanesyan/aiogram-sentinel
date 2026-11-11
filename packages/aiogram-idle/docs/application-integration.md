# Application-owned sessions, isolation and drafts

Idle does not require navigation. The public `FlowAdapter` describes resumability,
resume, abandon and tray restoration; the application continues to own business
drafts, authentication and FSM data. Use the [external session example](https://github.com/ArmanAvanesyan/aiogram-idle/blob/main/examples/external_sessions.py)
for an executable ordinary-handler or FSM integration:

```sh
python -m pip install 'aiogram-idle[redis]==0.2.0'
python examples/external_sessions.py --help
# From a checkout, with BOT_TOKEN set in the environment:
python examples/external_sessions.py --controls inline
python examples/external_sessions.py --fsm --controls hybrid --timezone Europe/Berlin
```

The example uses in-process application sessions and memory storage deliberately.
It is not a persistent authentication service. No token is read and no logging is
configured on import. All four prompt control styles are supported, and `--help`
does not need a token. The example's 30-second policy is explicitly enabled;
library idle creation remains disabled by default.

## Read-only session authority

Supply an object implementing `SessionAuthority.current(CoordinationKey)` to
`IdleRuntime(session_authority=...)`. Return an immutable `ExternalSession` or
`None` when the application has no authorized session. The contract is exported
by both Idle and `aiogram-coordination`:

```python
from aiogram_coordination import CoordinationKey, ExternalSession


class ExistingSessions:
    def __init__(self, store):
        self.store = store

    async def current(self, key: CoordinationKey) -> ExternalSession | None:
        current = await self.store.read_current_session(key)
        if current is None:
            return None
        return ExternalSession(
            session_id=current.id,
            revision=current.revision,
            absolute_expires_at=current.absolute_expiry_ms,
            idle_expires_at=current.idle_expiry_ms,
        )
```

`store` is the application's existing service; adapt its public fields explicitly.
Both expiries are UTC epoch **milliseconds**, not seconds or naive datetimes.
The effective deadline is the earlier expiry. IDs must not be reused, and absolute
expiry cannot change under the same ID. Revision is an opaque nonempty string.
An unavailable service must raise, never return `None`. Idle wraps lookup failure
as `SessionAuthorityUnavailable`, preserving recovery evidence and retrying later
without treating the failure as logout or running abandonment.

Before selecting external mode, explicitly activate storage format 2 as described
in [Redis storage](redis.md). Idle projects the external ID onto its own internal
generation, with the original absolute expiry. It does not create, extend,
replace or clear the application's session and does not clear FSM data on expiry.
Authority is rechecked before activity acceptance, controls and external effects.
A replaced/expired session cannot resume an older flow. Unresolved old effects
remain retained and may require reconciliation before a new flow is admitted.

## Explicit successful activity

Register a descriptor once rather than constructing activity snapshots in every
handler:

```python
from aiogram_idle import ActivityRegistration

editing = ActivityRegistration("draft.editing", policy_id="draft", adapter_key="application")
# Inside an installed, protected handler after application validation:
activity = await idle_context.activate(editing, operation_id="stable-application-operation")
# After a later successful edit:
activity = await idle_context.touch(
    expected=activity.guard, operation_id="stable-successful-edit-operation"
)
```

Pass the previous guard when replacing an existing activity. Use stable operation
IDs for retries; the same ID must not describe different caller intent. A received
update, failed validation or rejected application write must not count as activity.
Library-owned mode still requires an explicitly opened session before activation.
In external mode, `open_session` and `replace_session` reject the operation.

## Share the real FSM lock

Construct the Dispatcher with an explicit wrapper. The installer never swaps its
isolation silently:

```python
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram_coordination import TrackedEventIsolation

application_lock = SimpleEventIsolation()
dispatcher = Dispatcher(events_isolation=TrackedEventIsolation(application_lock))
runtime.install(dispatcher)
```

For cross-process FSM locking, reuse the application Redis client and key builder
with the renewable reference provider:

```python
from aiogram import Dispatcher
from aiogram_coordination import RenewableRedisEventIsolation, TrackedEventIsolation


def dispatcher_for_application(redis, application_storage, application_key_builder):
    application_lock = RenewableRedisEventIsolation(
        redis=redis, key_builder=application_key_builder
    )
    return Dispatcher(
        storage=application_storage,
        events_isolation=TrackedEventIsolation(application_lock),
    )
```

The supplied storage may remain the application's encrypted FSM implementation.
Its keys must preserve bot/chat/actor/field identity. Supported idle identity is
still actor-owned private chats with `FSMStrategy.USER_IN_CHAT`; this feature does
not silently add group, topic or business-message support.

A custom isolation implementation needs a public `IsolationProvider` that
references that exact isolation and returns a key-bound `LeaseHandle` with valid
ownership, an assertion and loss notification. Opaque fixed-TTL Redis locks are
not assumed to renew. The reference provider is an explicit application choice,
not an introspective wrapper around private aiogram Redis lock internals.

Handlers borrow proven ownership; workers acquire the same application lock.
The order is application isolation, then Idle's own storage coordination. Redis
commits retain their separate Lua ownership fence. Do not reacquire the application
lock recursively, bypass coordination after a Redis failure or swallow lease-loss
cancellation and continue business writes. Application session writes and business
FSM mutations must participate in this same boundary. A separate database is not
made transactional with Telegram or Redis by the wrapper.

## Timezones, events and shutdown

`TelegramPromptPresenter(quiet_hours=resolver)` accepts a per-conversation async
resolver `(key, at_seconds) -> bool`. `QuietHours(timezone, start, end)` is a reusable
IANA-zone implementation. Applications choose the timezone explicitly; there is
no guessed tenant timezone. UTC instants convert through `zoneinfo`, so repeated
local times in an autumn fold share the same quiet classification; nonexistent
spring-forward times have no corresponding instant. Midnight-spanning intervals
are supported. Quiet hours change sound delivery, not authentication or deadlines.

`on_event` receives immutable `IdleEvent(event_id, operation_id, outcome, key,
activity_key, at, prompt_id=None)` after commit; `at` is UTC epoch seconds.
`IdleOutcome` enumerates `shown`, `continued`, `cancelled`, `timed_out`, `restored`,
`delivery_unknown`, `failed`, and `session_expired`. Unknown adapter effects and
quarantine remain inspectable phases; their observational outcome is `failed`.
Events are best-effort observations, without a durable analytics outbox.

Use `coarse_event_sink` to map observational outcomes to application enums without
forwarding actor, node, activity or prompt identifiers. Internal diagnostic events
retain their identifiers for recovery. Sink failures cannot replay committed
delivery or business effects. Never send message text or credentials to analytics.

Managed installation stops the runtime before aiogram closes its FSM resources.
For an application-owned shutdown controller: stop new webhook/polling admission,
await `runtime.stop()`, drain protected handler work, close the backend, then close
FSM storage/isolation and application-owned Redis and Bot clients. Default
`shutdown_seconds` is 10 seconds. Unfinished effects retain their actual pending or
unknown evidence; a shutdown timeout does not mark them successful.

Unknown sends are suppressed by default. That avoids blind duplicate prompts but
does not guarantee eventual delivery. Explicit retry of ambiguous sends may cause
duplicates; reconcile using receipts and application idempotency evidence.
