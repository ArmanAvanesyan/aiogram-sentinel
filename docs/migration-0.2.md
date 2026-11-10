# Migrating from 0.1 to 0.2

## Dependencies and APIs

Install `aiogram-idle==0.2.0` alone for standalone use, or
`aiogram-idle[nav,redis]==0.2.0` for the optional combined integration.
The shared `aiogram-coordination>=0.1.0,<0.2` contract is mandatory;
Redis and Nav remain optional. Existing Idle coordinator imports remain
compatibility facades with Idle's exception family. Core imports never load Nav.
The previously exported but unused SessionAuthority protocol is now the shared
read-only `current(CoordinationKey) -> ExternalSession | None` contract.
Its timestamps are UTC epoch milliseconds; Idle's existing public snapshots
continue using seconds. Do not pass a seconds value to ExternalSession.

## Stage the storage upgrade

The default remains format 1, including its established record and lock keys.
Roll out 0.2 first with application-owned-session features disabled. Drain every
0.1 handler and worker, back up Redis and run the read-only assessment documented
in [Redis](redis.md). Only then explicitly activate format 2. Dry-run is the
default; actual activation requires `old_workers_drained=True` and a stable
operation ID. Bounded record migration is resumable and never invokes presenters
or application adapters. Pending effects, prompt tokens and operation receipts
remain intact. Old initialized writers are fenced by the changed namespace epoch;
new 0.1 processes cannot initialize an activated namespace. Downgrading binaries
against activated storage is unsupported. Use a compatible forward fix or a
coordinated backup restoration, never a prefix deletion.

## Application-owned sessions

Pass the authority when constructing IdleRuntime. The authority is read-only and
cannot be changed later. `open_session` and `replace_session` are unavailable in
this mode: the application owns those operations. `activate` projects an existing
session into an internal random generation, bounded by immutable absolute expiry.
The current application inactivity expiry is checked live, not captured as the
internal absolute deadline. A lookup outage raises SessionAuthorityUnavailable;
it never means logout, abandonment or permission to clear FSM state. Configure
webhook/error layers to propagate infrastructure exceptions appropriately.
Expired/replaced authority disables old work without invoking business cleanup.
A new session cannot overwrite unresolved effect evidence; recover or explicitly
resolve that evidence first. Authentication never extends merely to fit a prompt.
The [application guide](application-integration.md) includes a runnable adapter.

Application session mutations must use the same coordination domain. Reading an
external database while holding a Redis lock does not create a database transaction.
Library-owned sessions remain supported without an authority. Open one explicitly,
then call activate with an ActivityRegistration or continue using enter/touch.
Only successful explicit activity rearms deadlines.

## FSM isolation and lifecycle

Construct the Dispatcher with a public TrackedEventIsolation wrapper around the
application's lock/provider. Custom distributed providers must expose verifiable
lease ownership and loss; opaque unverified locks fail closed. USER_IN_CHAT and
actor-owned private conversations remain the supported identity scope. Keep bot,
chat, user and field identities distinct in custom FSM key builders.
Both incoming handlers and workers use the same normalized FSM lock before the
library's storage lock. The wrapper and underlying clients remain application-owned.
Stop admission, stop/drain Idle while FSM resources are live, drain protected
handlers, then close FSM and caller-owned Redis/Bot clients. Managed installation
orders Idle shutdown before aiogram's FSM close; manual lifecycle owners must do
so themselves. stop uses shutdown_seconds and retains unfinished intent on timeout.

## Optional navigation

Use Nav 0.2's public create_bindings_router factory for manual placement. Include
feature/state guards first, then the returned bindings router, then fallbacks.
Pass bindings_mode='manual' and the same bindings_router to the combined installer.
Intentional Dispatcher root handlers additionally require allow_root_handlers=True.
The default automatic mode remains strict. Reserved invalid callbacks are rejected
before application handlers; manual routing can intentionally leave valid controls
unhandled, which is reported rather than silently assumed successful.

Use ApplicationPresenter callbacks as the one owner of rendering and cleanup.
prepare_action/complete_render retains the render intent around application sends
and preserves Back/Cancel history semantics. track only adopts a completed render
and cannot recover a crash before tracking. The combined installer owns one
navigation/activity/deadline transaction, not a transaction with Telegram or the
application session database. Do not install the standalone middleware twice.

## Observation and delivery

IdleOutcome values document observable lifecycle outcomes. coarse_event_sink maps
only selected outcome strings into application analytics; conversation and node
identifiers need not leave the library. Observer failures never retry delivery or
business effects. AmbiguousSendPolicy.SUPPRESS remains the recommended default:
an uncertain send is retained for explicit recovery and is not automatically
repeated. This avoids blind duplicates but does not promise eventual delivery.
RETRY can duplicate a message and is an explicit application decision. Neither
backend promises exactly-once external effects.
