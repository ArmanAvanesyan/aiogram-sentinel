# aiogram-idle design and implementation plan

Status: proposed public API and implementation plan, 10 November 2026. This package has not been implemented.

Implementation status: the standalone memory and optional Redis aiogram-idle package is implemented locally at `/Users/armanavanesyan/oss/own/aiogram-idle`, with guarded contracts, lifecycle/worker, Telegram controls, examples and automated tests. See the [standalone installation recipe](../standalone-idle.md). Redis includes real-server concurrency, lease and crash-recovery tests. The optional navigation projection is now implemented locally with atomic memory/Redis component commits and combined coordination/recovery tests. Publication remains deferred; see the sibling package docs/navigation.md for supported installation and limits.

`aiogram-idle` tracks accepted conversation activity and applies explicit inactivity policies without requiring aiogram-nav. It can ask Continue/Cancel, invoke application cleanup/restoration, or leave an activity exempt. Navigation support is an optional integration. It supports reply-only, inline-only, command-only and hybrid bots with memory or Redis backends.

Read the [programme](index.md) and [storage specification](storage-and-verification.md). The [navigation plan](aiogram-nav.md) applies only to the optional integration.

## 1. Scope and safety guarantees

- One active inactivity lifecycle per idle conversation slot, independent of any navigation model.
- Idle owns conversation identity, activity/session generation and coordination contracts; adapters map external identity without changing scope.
- Accepted human activity refreshes the active deadline; background renders and analytics do not.
- A grace deadline is a separate phase and is never accidentally extended by generic middleware.
- Token-bearing inline controls cannot affect a different activity generation or session. Reply/command controls act only on the current authorized activity, but cannot prove which older prompt caused the input.
- Memory is for one process; Redis supports cooperating replicas.
- The package offers conditional state transitions and recoverable work, not exactly-once Telegram delivery.
- Business cancellation/resume is delegated to idempotent application adapters.
- Prompt creation is disabled by default, while existing prompt controls and recovery remain serviceable.

## 2. Independent activity and policy model

Core idle is activity-driven, not node-driven. It needs no registry, root, screen, navigation history or `aiogram_nav` model.

| Model | Fields and semantics |
| --- | --- |
| IdleConversationKey | Namespace, optional tenant scope, bot and normalized actor/chat context; idle-owned public type |
| ActivitySnapshot | session_id, activity_id, opaque activity_key, activity_revision, policy_id/version, adapter_key, JSON params, last_activity_at and expiry |
| IdleSnapshot | policy version, lifecycle phase, deadline, prompt receipt, pending operation and retry state |
| ActivityMutation | Operation ID, expected session/version, activity enter/touch/clear and accepted-activity flag |
| FlowContext | Idle identity, activity snapshot, prompt/operation IDs and freshly resolved application dependencies |
| ActionReceipt | operation_id, stage, effect receipts and disposition (rearm, disarm or replacement); no navigation target or renderer type |

An activity key is an application-defined identifier such as `form.entry`; it does not imply a tree or FSM state. Core policy selection is explicit by policy ID. Reject unknown policies/adapters and oversized or unserializable parameters. `touch()` does not create a session or silently replace an expired one.

```python
policies = IdlePolicies({
    "none": ExemptPolicy(),
    "draft": PromptPolicy(after_seconds=600, grace_seconds=600,
                          controls="reply"),
    "temporary-ui": QuietRestorePolicy(after_seconds=600),
})
```

| Policy | Behavior |
| --- | --- |
| ExemptPolicy | No idle job; invalidate the previous deadline |
| QuietRestorePolicy | After idle, invoke application cleanup/abandon/restore without asking |
| PromptPolicy | Ask, wait for grace, then resume or abandon/restore through adapters |

Policies contain intervals, control transport and delivery overrides. Activity entry selects an adapter; the adapter owns any destination or UI reconstruction. Parent inheritance and node-to-policy resolution exist only in the optional navigation integration. Core does not require application flow enums or business text.

## 3. Public API and standalone setup

Intended exports:

```python
from aiogram_idle import (
    IdleRuntime, IdleContext, IdleConfig, IdlePolicies,
    IdleConversationKey, ActivitySnapshot, ActivityMutation, ActivityGuard,
    SessionSnapshot, SessionGuard, FlowEligibility, ActionReceipt,
    ExemptPolicy, QuietRestorePolicy, PromptPolicy,
    FlowAdapter, PromptPresenter, IdleEvent, IdleStatus,
    ReplyPromptControls, InlinePromptControls, CommandPromptControls,
    QuietHoursResolver, AmbiguousSendPolicy,
)
from aiogram_idle.storage.memory import MemoryIdleBackend
from aiogram_idle.storage.redis import RedisIdleBackend
```

```python
backend = MemoryIdleBackend()
# Alternative: RedisIdleBackend(redis=redis, namespace="example-bot")
idle = IdleRuntime(
    backend=backend,
    policies=policies,
    adapters={"form": form_adapter},
    presenter=prompt_presenter,
    identity=idle_identity_resolver,
    isolation=isolation_adapter,
    dependencies=dependency_scope_factory,
    config=IdleConfig(enabled=False),
)
idle.install(dispatcher)

# Inside the handler that starts a new independent session:
session = await idle_context.open_session(
    operation_id=f"{update_operation_id}:open", lifetime_seconds=1800,
)
# After accepted application work, enter its first activity.
await idle_context.enter(
    "form.entry", policy_id="draft", adapter_key="form",
    params={"draft_id": "opaque-reference"},
    session_id=session.session_id, expires_at=session.expires_at,
    operation_id=f"{update_operation_id}:enter-form",
)
# Inside a later text handler, after validation/acceptance:
accepted_activity = await idle_context.current()
# Application rejects/restarts the flow if no live activity exists.
await idle_context.touch(operation_id=f"{update_operation_id}:accept-text",
                         expected=accepted_activity.guard)
```

`IdleContext` is injected as `idle_context` by the package's middleware. It also exposes `current()` and guarded `clear(reason=..., operation_id=..., expected=...)`; clear invalidates idle jobs and controls without discarding business data. Runtime `for_conversation(key)` creates the same context for trusted non-update callers, with explicit identity and coordination. Stable operation IDs make retries distinguishable from fresh activity.

```python
class IdleContext:
    async def open_session(self, *, operation_id: str,
                           lifetime_seconds: int) -> SessionSnapshot: ...
    async def replace_session(self, *, expected: SessionGuard,
                              operation_id: str,
                              lifetime_seconds: int) -> SessionSnapshot: ...
    async def current(self) -> ActivitySnapshot | None: ...
    async def enter(self, activity_key: str, *, policy_id: str,
                    adapter_key: str, params: JsonObject,
                    session_id: str, expires_at: datetime,
                    operation_id: str, expected: ActivityGuard | None = None
                    ) -> ActivitySnapshot: ...
    async def touch(self, *, operation_id: str,
                    expected: ActivityGuard) -> ActivitySnapshot: ...
    async def clear(self, *, reason: str, operation_id: str,
                    expected: ActivityGuard) -> None: ...
```

The application supplies an opaque session generation or uses `await idle_context.open_session(operation_id=..., lifetime_seconds=...)`, which returns a random session_id, expiry and guard without requiring FSM/navigation. `enter(expected=None)` is create-only: a live activity is a conflict. Replacing a live activity requires its current guard; replacing a session requires an explicit guarded `replace_session()` and invalidates old jobs/controls. An activity has a fresh random activity_id on every enter, even when session_id/activity_key are unchanged. A guard binds session_id, activity_id and activity revision; a clear result retains a tombstone rather than making old guards valid again. Context caches are not guards; callers reload after conflicts. Untrusted controls cannot create/replace sessions. Replayed old session IDs are rejected within retained tombstone/idempotency windows; outside those windows the application must enforce its session authority. Context mutations acquire the coordinator when called independently, and borrow it when middleware or an adapter already holds it.

`ActivitySnapshot.guard` and `SessionSnapshot.guard` expose immutable expected-generation values. `open_session()` is create-only unless a matching operation receipt exists. An externally supplied session ID is admitted only through an application SessionAuthority adapter (configured on IdleRuntime); it cannot reset absolute expiry through enter/touch. `touch()` refreshes last_activity_at, not authentication lifetime. Operation IDs are stable per logical substep, not regenerated on retry.

Core enter/touch/clear atomically persist accepted activity and its deadline in the chosen idle backend. They do not make the application's database or FSM update atomic. If activity originates in a separate durable store and must survive a crash before idle is informed, use an application outbox with replay/deduplication or a documented integrated transaction adapter. Plain middleware hooks cannot promise cross-store atomicity.

Public runtime methods:

```python
class IdleRuntime:
    def for_conversation(self, key: IdleConversationKey) -> IdleContext: ...
    async def apply_config(self, *, expected_generation: str,
                           update: ConfigUpdate) -> ConfigManifest: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def run_once(self, *, limit: int | None = None) -> PollReport: ...
    async def inspect(self, key: IdleConversationKey) -> IdleStatus: ...
    async def continue_current(self, context: ControlContext) -> ControlResult: ...
    async def cancel_current(self, context: ControlContext) -> ControlResult: ...
    async def reconcile(self, *, limit: int = 100) -> ReconcileReport: ...
```

`run_once()` supports deterministic tests and externally managed lifecycle. `install()` adds the idle control router, context and lifecycle hooks without importing navigation. Manual lifecycle mode skips hooks; double installation is rejected. Redis clients supplied by callers remain caller-owned; a `from_url()` factory closes its internally created client.

### Optional aiogram-nav integration

Install `aiogram-idle[nav]` or `aiogram-idle[nav,redis]`. Neither base idle nor its Redis extra installs navigation. Optional imports stay inside `aiogram_idle.integrations.nav`; exporting the core must not import that module.

| Distribution selection | Runtime dependencies |
| --- | --- |
| aiogram-idle | aiogram; no Redis or aiogram-nav requirement |
| aiogram-idle[redis] | Core plus Redis client; no aiogram-nav requirement |
| aiogram-idle[nav] | Core plus compatible aiogram-nav |
| aiogram-idle[nav,redis] | Both optional integrations |

Importing the optional adapter when its required aiogram-nav version is missing raises an actionable installation error; installed extras are not runtime feature flags. Core import, policy evaluation, controls and standalone memory/Redis workers remain unaffected.

```python
# Construct idle as above, but let the integration own installation.
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies

integration = NavigationIntegration(
    idle=idle,
    registry=registry,
    policies=NodePolicies(default="none", overrides={"form": "draft"}),
    adapters={"form": navigation_form_adapter},
    identity_mapping=identity_mapping,
)
navigation = Navigation(
    registry=registry,
    repository=integration.navigation_repository,
    presenter=screen_presenter,
    identity=nav_identity_resolver,
    isolation=isolation_adapter,
)
integration.install(dispatcher, navigation=navigation)
```

This is an alternative installation path, not a retrofit after standalone workers start. Construction and validation precede startup. Compatible already-installed context hooks may be reused before startup; hot-swapping record ownership is unsupported.

The integration maps node/params into opaque activities, resolves policy inheritance through registry parents, maps nav identity into idle identity, and supplies screen-aware resume/restore adapters. Its repository projection commits navigation and idle through one backend CAS/index operation. Standalone enter/touch/clear writes are rejected for a slot owned by this projection; activity from business handlers uses `integration.touch(key, operation_id=..., expected=...)` with the current mapped guard so both revisions remain coherent. Only integration modules know NavigationSnapshot or navigation renderer types.

The integration owns an optional opaque `components["aiogram_nav"]` record section. Core idle treats it as versioned JSON and never interprets node IDs. The adapter validates its schema and participates in the same commit. There is one writer path for the integrated record; do not install an independent nav repository against it. Standalone idle has no navigation component.

`integration.install()` connects adapter hooks and checks shared identity/isolation; it delegates base runtime installation if not yet installed and must not register duplicate routers/lifecycle hooks. Startup fails if required navigation is missing, identities cannot map losslessly, or two different repository writers are configured.

Public failures distinguish ActivityConflict/VersionConflict, SessionExpired, OwnershipLost, OperationIdConflict, PersistenceUnavailable, CommitUnknown, EffectUnknown, ConfigurationMismatch and UnsupportedContext. User-facing responses are application-localized; exception text contains safe identifiers only.

## 4. Flow and prompt adapter contracts

```python
class FlowAdapter(Protocol):
    async def inspect(self, context: FlowContext) -> FlowEligibility: ...
    async def resume(self, context: FlowContext,
                     *, operation_id: str) -> ActionReceipt: ...
    async def abandon(self, context: FlowContext,
                      *, reason: str, operation_id: str) -> ActionReceipt: ...
    async def restore(self, context: FlowContext,
                      *, reason: str, operation_id: str) -> ActionReceipt: ...

class PromptPresenter(Protocol):
    async def show(self, request: PromptRequest) -> PromptReceipt: ...
    async def finish(self, request: FinishRequest) -> DeliveryReceipt: ...
    async def strip(self, receipt: PromptReceipt) -> DeliveryReceipt: ...
```

Resume reloads and authorizes application state, then reconstructs its UI through ordinary application code. Abandon clears only the owned activity's state. Restore presents the application-defined post-cancel/timeout UI; no main menu or navigation target is prescribed. A no-op adapter is permitted for actions an application does not need. All durable effects must be idempotent for the supplied operation ID.

Action receipts checkpoint completed effects. Each effect has a stable stage ID; business idempotency does not imply Telegram-send idempotency. Custom adapters must use the supplied effect recorder or provide queryable stage receipts. Otherwise a crash inside that adapter is parked as EFFECT_UNKNOWN, rather than replaying the whole adapter. After resume, runtime uses the adapter-reported disposition: rearm the existing activity, disarm, or atomically accept a staged replacement activity. A replacement is a staged intent returned in ActionReceipt, committed with operation completion; adapters must not call public enter/go to erase their own in-flight operation. Replacement revisions win over stale rearm. The optional nav adapter uses operation-scoped prepare/checkpoint/complete for the same reason. Restore success defaults to disarmed, but a staged replacement activity is preserved. Adapter calls share an already-coordinated context and cannot reacquire a non-reentrant conversation lock.

FlowContext contains idle-owned activity identity/params and dependency scope, not a node, NavigationContext or synthetic update. The optional nav adapter translates this contract into screen rendering. FSM/custom-store adapters use it without navigation.

FlowContext also supplies a task-scoped coordinator capability and operation-scoped effect recorder. Continue counts as accepted human activity exactly once on completion; rearm uses its backend-recorded answer time and preserves logical expiry. Worker refresh/restore does not count as human activity. `inspect()` returns FlowEligibility(resumable, authorized, expires_at, recovery_kind) without side effects.

PromptReceipt contains idle-owned message references, control transport, prompt ID, locale, shown_at and optional keyboard metadata. Neither its models nor presenter contracts import aiogram-nav. Failure of nonessential inline cleanup does not prevent semantic abandonment; retain cleanup work separately.

## 5. Interaction styles and prompt controls

| Bot style | Default question controls | Continue | Cancel/timeout restoration |
| --- | --- | --- | --- |
| Reply only | New message with Continue/Cancel reply tray | Application adapter resumes UI and replaces temporary tray | Application restore adapter installs its reply tray |
| Inline only | New question with inline buttons | Remove/disable prompt controls and invoke resume adapter | Edit outcome and invoke application restore adapter |
| Commands only | New question naming `/continue` and `/cancel` | Resolve current prompt and invoke resume adapter | Close current prompt and invoke application restore adapter |
| Hybrid | Explicitly choose inline, reply or commands | Restore the application's declared presentation | Restore inline content and reply tray as separate operations if needed |

Do not implement reply-only support by quietly introducing inline buttons. Provide the actual reply and command transports in 0.1.

Reply text and commands do not carry a prompt ID. Bind them to the current authorized server-side prompt and current session. A delayed message saying Continue could apply to a later currently open prompt; this is an inherent transport limitation. Document it, keep actions non-destructive, and offer inline transport when strict prompt-specific binding is required.

While a prompt is open, reserved reply labels take precedence over business free text. Match only the current prompt's locale and explicitly retained installed-tray locale. If the application needs to accept the literal word Continue as business input, it must choose commands or inline controls, or require an explicit escape convention. Do not silently guess intent.

Inline controls encode a short opaque prompt token and action, with server-side actor/session binding and a bounded retention period. Acknowledge every callback, including stale and denied ones. Stripping stale inline markup is best-effort and never changes a newer session.

`/cancel` without a current prompt delegates to ordinary application cancel behavior; navigation is used only if configured. `/continue` without a current prompt gives an inert localized response. Do not register duplicate global cancel handlers in both libraries.

## 6. Activity and timing semantics

Default accepted activity is a successfully authorized application action or explicitly accepted draft input. `IdleContext.touch()` handles draft typing without any screen model. The optional nav adapter maps accepted navigation mutations to the same idle activity semantics. Activity acceptance is explicit, never inferred from every incoming update. Coordinate the entire relevant handler, including application state changes; locking only the trailing touch call permits a timeout to abandon a draft while that handler edits it. A rejected update, rate-limited update, stale callback, membership update or background job does not reset inactivity.

When ordinary activity arrives during PROMPTED, the default is supersede-on-success: under the conversation coordinator, let the application validate/process the input, then atomically accept activity and invalidate the prompt. A failed or rejected handler leaves the prompt/grace state intact. Explicit Continue/Cancel are reserved before effects and never fall through to business input. Applications requiring pre-handler admission can use a separately recorded admission intent; generic middleware must not assume every update succeeded. A failed business handler does not falsely commit replacement activity; prompt cleanup/recovery remains explicit. Applications can choose require-explicit-answer for forms where free text must not resume implicitly.

Use absolute stored deadlines and a backend clock. Redis commits and claims use Redis TIME; memory uses an injected clock. The grace period is anchored to Telegram's returned message timestamp, validated against backend time and expiry; persisting a late receipt never extends it. For custom presenters without a server timestamp, use the durably recorded request-start time conservatively. In-memory waiting uses monotonic time; backend wall clocks must be monitored for jumps. Retrying a failed send does not consume the user's response window.

Session and draft expiry are independent. Validate idle + grace + bounded delivery/processing slack against available logical lifetime, and recheck actual remaining lifetime before sending a question. Recovery retention is a storage duration after effects and is not part of the required user session lifetime. If a full grace period cannot fit before known session/draft expiry, skip the question and invoke the configured expiry-safe recovery; do not silently shorten grace or extend authentication. Absolute session expiry can still win after late activity; never extend an absolute authentication limit to preserve a draft. Before showing a question, call `FlowAdapter.inspect(context)` to confirm authorization, resumability and the known draft expiry without side effects. Missing drafts invoke expiry-safe restoration without sending a misleading Continue question. Recheck on Continue. Policies without a draft can return resumable=True with session-bounded expiry.

## 7. Lifecycle

| State | Trigger | Next state and effect |
| --- | --- | --- |
| DISARMED | Accepted activity/entry with active policy | ACTIVE with generation-specific deadline |
| ACTIVE | Accepted activity | ACTIVE with new activity revision and deadline |
| ACTIVE | Prompt due | PROMPT_PENDING with durable send intent |
| PROMPT_PENDING | Confirmed question sent and receipt saved | PROMPTED with grace deadline |
| PROMPT_PENDING | Ambiguous send | DELIVERY_UNKNOWN; no blind resend by default |
| PROMPT_PENDING | Definite send rejection/retry-after | Retry the same send stage when eligible; no grace yet |
| DELIVERY_UNKNOWN | Valid prompt-specific inline answer | Resume/cancel with proof of receipt; generic reply/command handling is described below |
| Any reserved effect | Ambiguous custom adapter effect | EFFECT_UNKNOWN; query stage receipt or quarantine |
| Any recoverable operation | Retry budget exhausted | QUARANTINED with retained diagnostic receipt and no automatic business effect |
| PROMPTED | Continue wins conditional transition | RESUMING, then ACTIVE or DISARMED |
| PROMPTED | Cancel or grace expiry wins | ABANDONING, then DISARMED after application restoration |
| ACTIVE | Quiet restore due | RESTORING, then DISARMED after application restoration |
| Any live state | Expired/replaced session | Invalidate jobs and controls; no old-flow mutation |

Transient states carry operation IDs, expected revisions and retry information. First-release recovery uses persisted stage checkpoints; a custom adapter unable to expose them must explicitly declare non-replayable behavior and accept EFFECT_UNKNOWN quarantine. An operation ledger checkpoints business and delivery stages. Errors do not revert to ACTIVE automatically and repeat an already executed business action.

Control processing and polling share the conversation coordinator. A Continue racing with timeout has one conditional winner; the loser reloads and returns a stale result. If application restoration fails after successful abandonment, retain restoration work without repeating confirmed abandonment. Unconfirmed restoration sends follow the same unknown-effect policy as questions. The same rule applies to optional navigation rendering.

## 8. Delivery, quiet hours and errors

The question is always a new message. Quiet hours set `disable_notification=True`; they do not defer the deadline by default. Outcome text can edit the question. Reply-keyboard restoration still needs a message carrying the new keyboard. Telegram documents silent delivery as notification without sound, not absence of notification. See [sendMessage](https://core.telegram.org/bots/api#sendmessage).

`QuietHoursResolver` returns a timezone and local interval per tenant/user according to application policy. Default is disabled. Validate IANA zones and intervals; test midnight crossing and DST. Do not use the process timezone or the chat viewer's timezone implicitly.

| Error | Treatment |
| --- | --- |
| Telegram retry-after | Persist retry time; release claim; respect retry-after plus bounded jitter |
| Definitive bot-blocked/forbidden | Terminate delivery for that conversation, emit unreachable hook; abandon only through explicit application policy |
| Missing/uneditable prompt | Mark cleanup unavailable; continue semantic transition; optional new outcome delivery is configurable |
| Network timeout after request may have been sent | DELIVERY_UNKNOWN; default suppress automatic resend |
| Redis unavailable before action | No background Telegram/business side effect |
| Redis unavailable after external effect | Preserve uncertainty; reconcile operation IDs on recovery |

An explicit at-least-once resend option may trade duplicates for missed questions. `AmbiguousSendPolicy.SUPPRESS` is the default. An unknown question send is not reported as `shown`; retain it until accepted user activity or a bounded recovery action, with no automatic draft destruction based only on the ambiguous question. A valid inline token prepared before sending can prove which prompt was received; authorize and bind its message reference before accepting it. Reply text and bare commands cannot prove delivery: while DELIVERY_UNKNOWN they may count as explicit current-activity input, but cannot retroactively emit shown or authorize inactivity abandonment. Declared explicit cancellation remains an application action.

## 9. Configuration and events

```python
IdleConfig(
    enabled=False,
    poll_seconds=10,
    concurrency=8,
    claim_limit=8,
    lease_seconds=60,
    renew_seconds=15,
    operation_timeout_seconds=45,
    lock_wait_seconds=5,
    shutdown_seconds=10,
    retry_max_attempts=5,
    retry_max_age_seconds=300,
    recovery_retention_seconds=3600,
    ambiguous_send=AmbiguousSendPolicy.SUPPRESS,
)
```

These are proposed defaults requiring load tests. Initial namespace bootstrap may create a config manifest from these settings; later startup validates compatibility and never silently overwrites an existing manifest. `apply_config()` is a trusted administrative CAS operation, not an exposed user command. Validate positive bounds, claim_limit <= available worker capacity, renew interval well below lease, and operation/lock deadlines against the renewal budget. Lease renewal must remain active through awaited work. Retention is distinct from business session lifetime.

`enabled=False` disables new prompt and quiet-restore creation. Existing prompts and recovery drain under persisted policy snapshots. Retry exhaustion transitions to QUARANTINED; deploys must not reset counters or silently discard work. Retry-after never permits an earlier send, even when its retry-age budget expires. Worker pause is separate from disablement. See the distributed configuration contract in the storage document.

Emit immutable events with event ID derived from operation ID and transition kind, operation ID, prompt ID where applicable, opaque activity key, policy ID, outcome and timing. Optional integration metadata can add a node ID or application flow label; neither is required by core. Outcomes include shown, continued, cancelled, timed_out, restored, superseded, delivery_unknown and failed. Application adapters can map them into a smaller analytics contract.

Hooks are observational by default: a metrics outage does not repeat a Telegram send. Reliable analytics require an optional durable outbox and consumer deduplication, not a claim that an in-process callback is durable. Do not log draft text, raw callback tokens or credentials; debug mode logs safe revisions, stages and lease identifiers.

## 10. Repository structure

```text
aiogram-idle/
  pyproject.toml
  README.md
  LICENSE
  CHANGELOG.md
  mkdocs.yml
  src/aiogram_idle/
    __init__.py
    py.typed
    config.py
    policies.py
    models.py
    runtime.py
    machine.py
    coordinator.py
    worker.py
    recovery.py
    adapters.py
    identity.py
    activity.py
    events.py
    errors.py
    controls/{base,reply,inline,commands,router}.py
    delivery/{presenter,quiet_hours,errors}.py
    storage/{base,memory,redis,codec}.py
    integrations/nav/{__init__,mapping,policies,repository,adapters}.py
    storage/lua/{commit,claim,renew,finish,reconcile}.lua
    effects.py
    sessions.py
  tests/{unit,contract,integration,failure,typing}/
  examples/{standalone_handlers,standalone_fsm,reply_only,inline_only,commands_only,hybrid,optional_nav}/
  docs/{quickstart,policies,lifecycle,redis,recovery,migration}.md
  .github/workflows/{ci,docs,publish}.yml
```

## 11. Implementation work packages

| ID | Work | Dependency | Completion evidence |
| --- | --- | --- | --- |
| IDLE-01 | Idle-owned identity/activity contracts, explicit policies and transition reducer | M0 | No nav imports/types; fake-clock transition and config tests |
| IDLE-02 | Standalone memory backend, session factory, guarded enter/touch/clear API | IDLE-01 | Atomic activity/deadline tests with aiogram-nav absent |
| IDLE-03 | Standalone flow/presenter adapters and four control transports | IDLE-02 | Ordinary-handler/FSM examples and all control transports without nav |
| IDLE-04 | Worker lifecycle, capacity limits and deterministic run_once | IDLE-02/03 | No sleeps in unit tests; clean shutdown and no leaked tasks |
| IDLE-05 | Standalone Redis commits, claims, renewal and operation ledger | IDLE-04 | Real-Redis contract/crash tests with aiogram-nav absent |
| IDLE-06 | Ambiguous delivery, retry classification and reconciliation | IDLE-05 | Inject failure at every external-effect boundary; no blind replay |
| IDLE-07 | Telemetry, health reporting and optional outbox extension point | IDLE-06 | Hooks cannot duplicate effects; backlog and unknown-delivery metrics |
| IDLE-08 | Optional nav adapter, inheritance mapping and atomic projection | IDLE-06/07, NAV-07 | Combined repository contracts; neither core gains a mandatory dependency |
| IDLE-09 | Independent package candidate, recipes and Kit compatibility tests | IDLE-06/07; IDLE-08 only for nav extra | Standalone artifact matrix plus separately gated combined matrix |

## 12. Test obligations

- Core explicit policy selection and all timing phases under an injected clock; inheritance is tested only in the nav adapter.
- Core wheel and Redis extra install/run with aiogram-nav absent; adapter dependencies/import failures are tested separately.
- Plain-handler and FSM-only examples execute the full lifecycle without nodes or a registry.
- Prompt markers allow grace expiry; they suppress only an inappropriate second question.
- Accepted draft typing resets inactivity without changing application draft content.
- Generic updates cannot accidentally rearm a grace deadline.
- Reply/command controls bind only to the current authorized prompt; ambiguous text policy is demonstrated.
- Inline controls reject wrong actor, bot, tenant, session, prompt and expired generation.
- Continue/Cancel/timeout races have one semantic winner.
- Rate limits respect retry-after without holding a sleeping batch claim.
- Crash before send, after send, before receipt persistence, after abandon and during restoration each follows the operation ledger.
- Session/activity ABA, repeated keys, stale guards and delayed old-session input cannot overwrite a newer generation.
- Session expiry, absolute expiry and draft expiry never mutate a recreated session.
- Short remaining lifetime skips a prompt; recovery retention does not force a longer user session.
- Flow inspection denies expired/revoked drafts before prompt delivery.
- Failed ordinary input preserves grace; successful explicit touch supersedes it once.
- Operation-ID payload mismatch is rejected; repeated substeps use distinct stable IDs.
- EFFECT_UNKNOWN, exhausted retries and late grace receipts remain observable and bounded.
- Redis outage suppresses idle effects; recovery does not cause a burst beyond capacity limits.
- Android, Desktop and iOS manual tests separately record sound, banner, unread state and tray behavior.

Release gates and the detailed failure matrix are in [storage and verification](storage-and-verification.md).

## 13. Illustrative consumer examples

An unfinished feedback form could select the draft policy, while a temporary settings panel could select quiet restoration. Another bot could use the same APIs for a survey or booking conversation. These examples do not define built-in activity IDs, mandatory destinations, analytics contracts or release dependencies. Consumers choose translations, timezone rules and business semantics.
