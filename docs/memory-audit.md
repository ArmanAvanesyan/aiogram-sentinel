# Memory implementation audit

This review checks aiogram-nav against the reviewed navigation and storage plans,
especially concurrency, partial-render recovery, callback ownership and FSM
integration. Redis implementation is covered separately in [the Redis guide](redis.md); this memory audit neither
adds a Redis backend nor couples navigation to aiogram-idle.

## Corrected findings

| Gap | Correction |
| --- | --- |
| Independent effect recorders could both execute one stage | Shared execution guards bind coordinator, live scope, conversation, operation and stage across recorders and Navigation instances |
| A nested recorder could wait on its own running stage | Live per-execution nonces reject recursion while allowing later cache reads from copied contexts; cancelled waiters release guard references |
| Permission changes during storage awaits could precede another send | Authorization and frozen parameter validation run again immediately before new protected effects |
| A rejected safe replay could downgrade earlier uncertainty | Older started/unknown evidence survives a later rejected or denied replay; only fresh, definitely rejected intent becomes not_sent |
| Low-level completion could replace confirmed message references | Completion must match the recorded full render receipt, including complete ViewState normalization |
| Screen preferences could override a refresh's fresh-send constraint | Explicit RenderRequest delivery constraints take precedence over ScreenSpec preferences |
| Cached partial receipts could coerce fractional/boolean IDs or trigger fallback from ambiguous data | Receipt schemas require exact positive integers, matching chats and unambiguous availability status before further effects |
| Malformed plans could silently drop markup | Recorded inline/reply/keep plans validate their shapes and types before delivery |
| Invalid global binding flags and decoders survived setup | Binding flags require booleans and command decoders must be callable |
| An old display locale could act as an installed keyboard locale | Installed-locale fallback requires an actual tracked reply keyboard |
| FSM storage or key layout could change after installation | Middleware verifies the original storage, key-builder signature and shared coordinator |
| Missing or substituted FSMContext could deadlock or borrow the wrong lock | Borrowing requires the original context/storage and normalized identity; missing contexts fail before recursive lock acquisition |
| Moving the binding router could silently change precedence | The installed router must remain attached before business routers |
| A resolver opting out of navigation could cause missing-context filter errors | Unscoped messages/callbacks fall through instead of executing navigation filters |
| Unsupported direct-message topic metadata could be collapsed into a private slot | Topic identity is rejected explicitly by the default private resolver |
| Positive sub-millisecond intervals truncated to zero | Durations round upward to integer-ms resolution; unrepresentable millisecond intervals fail configuration |
| Invalid persisted activity timelines and structured fields could survive construction | Models reject activity at/after expiry and malformed nested contract values |
| Floating actor IDs could alias integer ownership checks | Callback consumption requires an integer actor identity |

## Recovery and application contracts

Known receipts are retained even when a later commit or authorization check fails.
Permission loss does not prove an earlier uncertain request was never sent.
Automatic recovery still suppresses unknown non-idempotent sends by default.
The shared stage guard is process-local and scope-bound; it does not grant a child
task handler ownership or provide multi-process persistence.

Cancellation hooks own authorization and business-generation checks for their
external writes. The generic navigation authorizer governs destination access;
it does not replace a business service's permission checks. Hooks also need
idempotency for their operation ID. Unknown cancellation outcomes remain guarded
until application recovery resolves them from external evidence.

All protected handlers and explicit application rendering helpers must use the
shared coordinator. Direct low-level repository access remains an advanced API:
callers must supply guarded intent and must not execute business writes outside
the corresponding coordination scope.

FSM strategy, event isolation, storage/key mapping and binding-router placement
are setup-time configuration. Change them through an explicit drain/reinstallation
or application migration, rather than mutating them under active handlers.
An identity resolver may return None to exclude a context; navigation bindings
then defer to application routers. Application code remains responsible for those
excluded contexts.

## Verification

See [the verification report](verification.md) for the final suite, coverage,
compatibility and clean-install results. New tests use actual Dispatcher updates,
recording Telegram sessions, deterministic effect barriers, receipt tampering and
permission changes during storage checkpoints. They cover the corrected paths
without making real Telegram requests.

Memory remains single-process and non-durable. Redis was deferred at this audit’s
completion and is now implemented separately. Optional idle integration, durable
analytics and real Telegram-client UX qualification remain deferred.
No lease or local guard can retract an already in-flight external request.
