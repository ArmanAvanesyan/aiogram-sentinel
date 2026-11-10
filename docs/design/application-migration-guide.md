# Adopting the standalone aiogram libraries

## Release availability

Sentinel 1.2.0, Cmds 0.2.0, Coordination 0.1.0, Nav 0.2.0 and Idle 0.2.0
are published. Use matching tagged examples with these versions; all release
artifacts were verified against their PyPI hashes and clean installed profiles.

## Choose only the responsibilities needed

| Package | Library owns | Application owns |
| --- | --- | --- |
| Sentinel | middleware policies, rate/debounce counters, error routing | handler semantics, bucket selection, webhook failure response |
| Cmds | command profile rendering and Telegram menu calls | profile selection, locale, scope, confirmed fingerprint persistence |
| Coordination | normalized identity, task ownership and lease proof | Dispatcher construction, isolation provider, resource lifecycle |
| Nav | registry, transitions, view/control ownership and recovery | authentication, business drafts, optional rendering/cleanup |
| Idle | activity deadlines, prompt lifecycle and recovery | flow adapters, successful activity decisions, wording/timezone |

Neither Nav nor Idle requires the other. Redis is optional. Memory backends are
single-process and lose state on restart. Kit is not required to install them.

## Migration order

1. Add Sentinel to the ancestor router that actually contains protected handlers.
   Keep existing defaults unless deliberately selecting action-kind policies.
   Configure infrastructure exceptions to propagate when webhook retries depend
   on a failing HTTP response. Test policy propagation using real updates.
2. Adopt Cmds generic profiles. Choose the description locale separately from the
   Telegram language slot: `language_code=None` omits that slot. Explicitly clear
   obsolete language-specific menus when migrating. Save a fingerprint only after
   confirmed application; preserve partial failure results.
3. Construct the Dispatcher with `TrackedEventIsolation(application_isolation)`.
   For custom isolation provide the public lease provider. A fixed-TTL opaque lock
   does not prove continued ownership. Do not silently replace application storage.
4. Supply a read-only `SessionAuthority` returning `ExternalSession` with epoch
   millisecond expiry values. Return `None` only for absence; raise on outages.
   Never reuse session IDs or extend absolute expiry under an existing ID.
5. Adopt Nav independently if useful. Include `create_bindings_router(navigation)`
   after state guards and before fallbacks; install with `bindings_mode="manual"`
   and that same router. Root handlers require explicit manual-mode approval.
   Use `ApplicationPresenter` for one application-owned cleanup implementation.
   Prefer prepared actions for recoverable sends; `track()` cannot recover a send
   that happened before tracking was recorded.
6. Adopt Idle independently through `FlowAdapter`. Register reusable
   `ActivityRegistration` descriptors and call `idle_context.activate`/`touch`
   only after successful business operations. Incoming updates alone are not
   successful activity. Keep creation disabled until the adapters are tested.
7. If both are needed, use the combined installer and shared repository boundary.
   Its navigation/activity commit is atomic; Telegram, an external session service
   and business databases are not part of that transaction. Do not install the
   runtimes independently and assume unrelated writes are atomic.

## Deployment and failure handling

Keep application FSM isolation outside library storage coordination in the lock
order. Handlers borrow proven ownership; workers acquire the same normalized lock.
Do not swallow ownership-loss cancellation and continue business writes.

Before external-session mode, stage storage format 2: deploy compatible readers,
drain old writers, back up and inspect storage, then explicitly activate under
locks and compare-and-swap. Do not run old writers against an activated namespace.
Managed Redis attestations may supply unavailable introspection facts, never
contradict observed configuration. Redis errors do not trigger a memory fallback.

Unknown sends are suppressed by default; inspect and reconcile evidence instead
of blindly retrying a possibly delivered prompt. Application adapters need stable
idempotency evidence for recoverable business effects. Events are observational,
not a durable analytics outbox; use coarse outcome mapping when identifiers must
not enter analytics.

Stop update admission, stop Idle, drain Nav and handlers, close library backends,
then close FSM isolation/storage and application-owned Redis/Bot clients. A drain
timeout does not turn unfinished effects into successful ones.

## Executable public examples and detailed contracts

- [Sentinel documentation](https://github.com/ArmanAvanesyan/aiogram-sentinel/tree/main/docs)
- [Cmds documentation](https://github.com/ArmanAvanesyan/aiogram-cmds/tree/main/docs)
- [Coordination contracts](https://github.com/ArmanAvanesyan/aiogram-coordination)
- [Nav application integration](https://github.com/ArmanAvanesyan/aiogram-nav/blob/v0.2.0/docs/application-integration.md)
- [Idle application integration](https://github.com/ArmanAvanesyan/aiogram-idle/blob/v0.2.0/docs/application-integration.md)

Use tagged examples against matching published versions after the release gate.
Examples cover ordinary/FSM handlers and reply, inline, command and hybrid controls.
Validate your actual router precedence, locale changes, stale/foreign callbacks,
Redis outage, session replacement and shutdown order before enabling production.
