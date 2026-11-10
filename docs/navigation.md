# Optional aiogram-nav integration

`aiogram_idle.integrations.nav` projects navigation onto the idle backend. The two
standalone libraries still work independently. Importing `aiogram_idle`, including
its Redis backend, does not import or install aiogram-nav. Navigation itself has
no idle dependency.

Install the integration in a bot environment:

```sh
python -m pip install 'aiogram-idle[nav]==0.2.0'
# Select both optional integrations when using Redis:
python -m pip install 'aiogram-idle[nav,redis]==0.2.0'
```

The `nav` extra resolves `aiogram-nav>=0.2.0,<0.2` from PyPI. Base and Redis-only
installations remain independent of aiogram-nav.

For source development, put compatible `aiogram-idle` and `aiogram-nav` checkouts
in adjacent directories and run the combined example from the idle checkout:

```sh
uv sync --frozen --extra nav --extra redis
uv run --no-sync python examples/navigation.py --style hybrid
```

Set BOT_TOKEN for the example. Set NAV_REDIS_URL to use Redis for both integrated
navigation and the example's application FSM store. Without it, storage is memory
and single-process. CLI help does not require either variable. All four styles
are available: reply, inline, commands and hybrid. Debug logging is configured by
the example, never globally by the library.

## Construction and installation

```python
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
from aiogram_nav import Navigation

integration = NavigationIntegration(
    idle=idle,
    registry=registry,
    policies=NodePolicies(
        default="none",
        overrides={"editor": "draft"},
        activities={"editor.rating": "editor", "editor.typing": "editor"},
    ),
    adapters={"editor": application_flow_adapter},
)
navigation = Navigation(
    registry=registry,
    repository=integration.navigation_repository,
    presenter=screen_presenter,
)
integration.install(dispatcher, navigation=navigation)
```

The referenced policy IDs must exist in `idle.policies`; `none` is an example
exempt-policy ID, not a reserved value. Policy overrides inherit through registry
parents. Activity grouping is an explicit exact-node mapping; dotted name prefixes
never imply membership. By default every node is its own activity.

Use **only** `integration.install`, before business Routers and before starting
workers. Do not first call `navigation.install` or `idle.install`; those create
standalone middleware with separate ownership assumptions. Duplicate installation,
multiple integration writers, incompatible registries, live coordinator changes,
unsupported isolation and lossy identity mapping are rejected. For headless
navigation/worker use, call `integration.bind(navigation)` instead and manage
`idle.start()` / `idle.stop()` yourself. Workers drain before shared FSM shutdown when the integration owns lifecycle. With application-owned shutdown, stop idle before closing shared stores.
`lifecycle=False` disables dispatcher
startup/shutdown hooks for tests or an application-owned lifecycle.

Application adapters supply eligibility (`inspect`) and idempotent business
cancellation (`abandon`). They do not own integrated screen reconstruction:
Continue re-renders the current node and restore renders its registry Cancel
destination. The integration records those effects and stages their navigation
result under the existing idle operation. The application cancellation hook gets a nested durable stage; its own `replay_safe` opt-in controls whether an unknown business effect may repeat. Application hooks must use the supplied
effect recorder or durable idempotency/version checks for their business writes.

## One authoritative record

The idle backend owns the session, activity, idle state, deadlines and operation
receipts. Navigation owns a versioned opaque `aiogram_nav` component containing its
snapshot, prepared actions, stage receipts and callback tokens. Core idle treats
that payload as JSON; only the optional adapter interprets it.

Every navigation mutation executes the normal navigation reducer, then commits its
component through an idle-owned conditional transaction. A completed accepted
navigation action updates its displayed location, activity and due scheduling in
that same transaction. No post-commit callback supplies the atomic guarantee.
Memory uses the existing backend lock; Redis uses the authoritative envelope CAS
and scheduling script. Network calls run outside backend locks.

Session IDs map to the same authoritative generation. Navigation expiry never exceeds that session’s absolute expiry and may be shorter; reconstruction never extends authentication. Navigation timestamps
use integer milliseconds; idle uses seconds, with conversion only at this boundary.
Both displayed activity revisions share one acceptance counter. Moving to a new
activity group creates a fresh activity ID; refresh/parameter changes within the
same group preserve it and accept activity once. Background rendering changes the
view without advancing accepted activity or extending its deadline. Exempt nodes
retain navigation but disarm ordinary idle prompts.

Standalone `enter`, `touch`, `clear` and session replacement cannot overwrite an
integration-owned activity. Business handlers use a mapped guard:

```python
record = await idle.inspect(integration.navigation_repository.mapping.to_idle(nav_key))
await integration.touch(
    nav_key, expected=record.activity.guard, operation_id="update:42:accepted-text"
)
```

Call this only after application processing succeeds. When a reply/hybrid prompt
has replaced the tray, touch also reserves a deterministic background render in
the same atomic transaction. It restores the application keyboard without
accepting activity twice; a crash leaves recoverable pending UI work. Duplicate
touch retries return the original activity receipt and do not render again. Use a distinct stable
operation ID for each logical action. `restart_activity` accepts the same guard
and explicitly starts a fresh activity generation within the current group.
An FSM write or external database update is not made atomic with idle by this
transaction. Use a durable producer outbox or an application transaction adapter
when that additional guarantee is required.

## Coordination and input precedence

One idle conversation coordinator covers handlers, navigation actions and workers.
The projection maps the complete namespace/tenant/bot/chat/actor identity into its
lock domain. Identity mappings must preserve every supported field and round-trip.
Built-in support is for actor-owned private chats; default FSM mapping cannot
represent tenant-specific state and rejects that setup.

The combined middleware runs after the FSM middleware, verifies its storage and
key mapping, borrows the actual held SimpleEventIsolation lock, then acquires the
shared distributed lock when applicable. Workers acquire locks in the same order.
Disabled FSM isolation still receives full-handler coordination. Use
`FSMStrategy.USER_IN_CHAT`, and `DefaultKeyBuilder(with_bot_id=True)` for a shared
Redis FSM store. Merely choosing Redis for navigation does not make a memory FSM
store shared across processes.

Active idle controls precede navigation bindings, then business input. Bare
/cancel falls through to the application when there is no idle prompt. Reply text
and commands have current-prompt provenance only; inline controls retain their
actor/session/activity/prompt or view ownership. Rejected callbacks acknowledge
without stripping keyboards whose ownership is unproven.

## Recovery and limits

Navigation prepare retains the old committed screen but suppresses idle prompts
about it while rendering is unresolved. Generic recovery scheduling retains the
pending component. A worker reuses confirmed rendering receipts; unknown sends,
expired authorization or denied reconstruction park the component rather than
resending automatically. Inspection retains the reason. Explicit recovery or a
new safe refresh can resolve the retained navigation operation; do not delete its
receipts to regain capacity.

Continue, timeout and Cancel reserve one idle operation. Their rendering uses that
operation's effect recorder and captured job claim. The navigation component and
idle lifecycle finish together. A crashed poller cannot discard its only recovery
job, and navigation checkpoints cannot replace a live worker's claim generation.
Temporary reply-keyboard provenance is invalidated when an idle prompt overlays
it. The canonical text presenter reinstalls the declared application keyboard,
or sends explicit removal if the reconstructed screen omits a keyboard. Custom
presenters receive `RenderRequest.dependencies["aiogram_idle.reply_overlay"]`
and must reconstruct or remove that temporary tray. Restoration requests also
carry `aiogram_idle.silent_restore`; the canonical text presenter sends them
silently, and custom presenters must honor that flag.
After commit, tracked obsolete inline controls are cleaned only under a live
coordination guard. Cleanup failures do not repeat business cancellation or sends.

Components and effect receipts have an absolute 8 MiB limit; `max_components_bytes`
can lower component admission. The complete persisted envelope is bounded at
32 MiB. The idle receipt budget is shared by preparation, effect checkpoints and completion,
not just completed screens. Configure it for the expected number of staged writes.
Receipt/history/control limits also apply; admission may reject before a
count limit if its byte bound is reached. Unresolved evidence is retained rather
than evicted. Redis requires a supported writable primary with noeviction; its
persistence and failover durability remain deployment responsibilities. Leases
cannot retract an in-flight Telegram request or fence arbitrary business stores.

## Verification

The combined matrix is separate from standalone checks. `coverage-nav.toml` and
`pyright-nav.json` include the optional modules; default standalone checks omit
them and remain runnable without the peer package.

```sh
uv sync --frozen --extra nav --extra redis
AIOGRAM_IDLE_REDIS_URL=redis://localhost:6379/0 AIOGRAM_IDLE_REQUIRE_REDIS=1 \
  uv run --no-sync pytest --cov=aiogram_idle --cov-config=coverage-nav.toml
uv run --no-sync pyright --project pyright-nav.json
```

For standalone development without a neighboring navigation checkout, keep the frozen lock (`uv sync --frozen`) and use `uv run --no-sync`; regenerating the development lock resolves all extras and needs the local peer source. Base and Redis-only distribution installs do not need it.

An automatic, separate integration CI job checks out `ArmanAvanesyan/aiogram-nav`
at `main`, runs the optional strict type profile and exercises navigation/component
tests with real Redis. Standalone jobs neither check out nor install navigation.
The manual optional-integration workflow accepts an explicit compatible peer
repository/revision and checks the broader Python 3.10–3.14 and Redis 8 matrix.
Configured jobs do not imply remote execution or package publication; consult
[dated verification evidence](verification.md) for what was actually run.
