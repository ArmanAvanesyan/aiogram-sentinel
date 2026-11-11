# aiogram-nav design and implementation plan

Status: reviewed plan, 10 November 2026. The standalone memory and Redis backends are implemented locally at `/Users/armanavanesyan/oss/own/aiogram-nav`; see the [installation recipe](../standalone-nav.md). The optional idle projection is now implemented locally in aiogram-idle; wider Kit integration milestones remain future work. Redis supports standalone primary deployments; see the sibling package Redis guide for operational limits. No distribution has been published.

`aiogram-nav` adds explicit screen identity, navigation actions and optional rendering/input helpers to existing aiogram 3 bots. Reply keyboards, inline keyboards, commands and hybrids use identical node IDs, state and permission checks. Redis is optional.

Read the [programme](index.md) and [storage specification](storage-and-verification.md) with this document.

## 1. Scope and invariants

- A node identifies a screen, independent of its entry route or keyboard style.
- A screen can have many entries: command, reply text, callback, application handler or external completion event.
- Structural parents provide grouping and inherited defaults; they do not define every allowed transition.
- Current location includes validated reconstruction parameters.
- FSM state and business drafts remain application-owned.
- No node change is committed simply because a handler was selected.
- Permissions and feature availability are rechecked on entry, resume and protected action execution.
- The library never treats a hidden button or unadvertised command as an authorization rule.
- One initial navigation slot per private conversation. Multiple independently active panels/stacks are deferred.

## 2. Domain model

Public models are immutable dataclasses unless stated otherwise. Parameters and stored metadata use a recursively defined JSON value type. Datetimes are UTC-aware at API boundaries; persisted timestamps are integer epoch milliseconds.

| Model | Fields and semantics |
| --- | --- |
| ConversationKey | namespace, tenant_id, bot_id and normalized aiogram identity; full definition in storage specification |
| Node | id, parent, back_to, cancel_to, renderer key, parameter validator, optional metadata |
| NavigationSnapshot | schema_version, session_id, node_id, params, nav_revision, activity_revision, entered_at, last_activity_at, expires_at, view, bounded history |
| ViewState | view_id, message references, reply keyboard semantic key, locale, render status |
| MessageRef | chat_id, message_id and role: content, controls or tray |
| EntryPoint | stable entry ID, destination/action, source kind and applicable node scope |
| NavigationAction | go, back, home, cancel or refresh, with validated parameters |
| NavigationEvent | action ID, old/new node, revisions, source and outcome; no draft data |

Use random session IDs so expired and recreated sessions cannot pass old callback guards. Navigation revision increases when location, parameters or view identity changes. Activity revision increases for accepted user activity, including draft input that does not change screens. Storage CAS versions are separate opaque tokens and change for every repository mutation. With the optional idle adapter, they also change for idle-only mutations; standalone nav does not depend on idle.

History is optional and bounded, default 20 entries. `back()` uses an explicit `back_to` first; otherwise a valid history entry; otherwise the configured root. `cancel()` uses the nearest explicit inherited `cancel_to`, never an inferred parent. Missing targets fail startup validation. A root Back action refreshes the root without appending another history entry.

Allow multiple roots for linked and guest contexts. Cross-root actions require an explicit target and authorization. Unknown persisted nodes resolve through a migration mapping or a configured safe-root recovery; never guess by splitting dotted IDs.

## 3. Registry and action API

Intended exports:

```python
from aiogram_nav import (
    Navigation, NavigationConfig, NavigationRegistry, Node,
    NavigationContext, NavigationSnapshot, ConversationKey,
    NavigationRepository, NavigationPresenter, RenderResult,
    MessageRef, InputBindings, ReplyEntry, CommandEntry,
    CallbackEntry, NavigationError,
)
from aiogram_nav.storage.memory import MemoryNavigationRepository
from aiogram_nav.storage.redis import RedisNavigationRepository
```

```python
registry = NavigationRegistry(
    roots={"main", "welcome"},
    nodes=[
        Node("main", renderer="main"),
        Node("settings", parent="main", renderer="settings",
             cancel_to="main"),
        Node("settings.language", parent="settings",
             renderer="language", back_to="settings"),
        Node("feedback", parent="main", cancel_to="main"),
        Node("feedback.rating", parent="feedback", renderer="rating"),
        Node("feedback.typing", parent="feedback", renderer="typing"),
        Node("welcome", renderer="welcome"),
    ],
)
registry.validate()
```

In this illustrative registry, abstract grouping nodes such as `feedback` have no renderer and cannot be direct action destinations. Validate uniqueness, parent and target existence, acyclic parents, root reachability, renderer availability and parameter schemas. Keep the registry immutable after startup.

```python
navigation = Navigation(
    registry=registry,
    repository=MemoryNavigationRepository(),
    presenter=presenter,
    identity=identity_resolver,
    isolation=isolation_adapter,
    config=NavigationConfig(history_limit=20),
)
navigation.install(dispatcher)
```

`install()` registers context middleware and explicitly requested input bindings. It does not attach rate limiting, change FSM storage, publish command menus or start an idle worker. Identity and isolation adapters are shared with application processing.

Public context methods:

```python
class NavigationContext:
    async def current(self) -> NavigationSnapshot | None: ...
    async def go(self, node_id: str, *, params=None,
                 history="push", source="application",
                 operation_id: str | None = None) -> RenderResult: ...
    async def back(self) -> RenderResult: ...
    async def home(self, *, root: str | None = None) -> RenderResult: ...
    async def cancel(self) -> RenderResult: ...
    async def refresh(self) -> RenderResult: ...
    async def track(self, node_id: str, *, params=None,
                    rendered: RenderResult) -> NavigationSnapshot: ...
    async def touch(self, *, source: str) -> None: ...
    async def prepare_render(self, node_id: str, *, params=None,
                             operation_id: str) -> PreparedAction: ...
    async def complete_render(self, prepared: PreparedAction, *,
                              rendered: RenderResult) -> NavigationSnapshot: ...
```

The registry above is a consumer example only; no listed flow, destination or policy is built into the library.

`go()` validates/authorizes, durably prepares the action, renders through a stage recorder, then completes the location commit. It never sends before its prepare succeeds. The old committed screen remains current until completion; controls for a prepared new view remain pending until completion or explicit recovery. `track()` adopts a successfully rendered view from existing screen helpers without sending it again. It is a weaker migration API: it cannot recover a render that happened before tracking if the process crashes. For crash-safe existing helpers, use `prepare_render()` before sending and `complete_render()` afterward. `touch()` records accepted activity without entering a new screen. All participate in the repository's mutation path. An optional adapter supplied by `aiogram-idle[nav]` can map these mutations to idle activity atomically; no idle package is imported by nav core.

For update-driven actions, the context derives stable action/substep IDs; direct callers provide them explicitly. All convenience actions accept an operation_id override even where the signatures above omit it for brevity.

`cancel()` coordinates an optional application cancellation hook before rendering the destination. The hook gets an operation ID and must be idempotent if it changes durable business state. Cancelling navigation never silently clears all FSM data.

## 4. Rendering and Telegram delivery

```python
class NavigationPresenter(Protocol):
    async def render(self, request: RenderRequest) -> RenderResult: ...
    async def cleanup(self, request: CleanupRequest) -> CleanupResult: ...

@dataclass(frozen=True)
class RenderResult:
    view_id: str
    messages: tuple[MessageRef, ...]
    reply_keyboard_key: str | None
    locale: str
```

Render requests contain operation ID, a stage recorder, target, parameters, current view, actor, bot, dependency scope and delivery preference. They never fabricate a Telegram Update for a background worker. Application services and locale are resolved afresh.

Provide an optional `TextPresenter` that maps renderer keys to application functions returning `ScreenSpec(text, inline_keyboard, reply_keyboard, reply_keyboard_key, delivery)`. `ScreenSpec` is a plan, not a raw unrestricted Telegram payload. Initial helpers handle text; custom presenters can support media and multiple messages.

| Screen output | Delivery rule |
| --- | --- |
| Text plus inline controls | Send or edit a compatible tracked content message |
| Text plus reply keyboard | Send a message carrying ReplyKeyboardMarkup |
| Text with both keyboards | Send inline content plus a separate tray message |
| Remove reply keyboard | Send an explicit ReplyKeyboardRemove message |
| Unchanged reply keyboard | Keep the tracked semantic keyboard key; do not resend merely to refresh inline content |
| External Mini App/URL | Track the launch screen; enter a completion screen only on a verified application event |

Telegram's sendMessage has one reply_markup field. A hybrid presentation is therefore potentially multiple API operations. A reply keyboard remains until replaced/removed; omission of reply_markup is not removal. Editing inline markup cannot install a reply keyboard. See [Telegram keyboard contracts](https://core.telegram.org/bots/api#replykeyboardmarkup).

Before each Telegram effect, record its stable stage ID and intent; after a confirmed response, record its receipt. A partial multi-message render returns or records a structured partial result. Do not claim atomic Telegram rendering. Successful full rendering commits the intended location; partial rendering leaves a recovery marker and known message references so recovery can retry only definite unsent/idempotent stages without trusting the intended target as fully displayed. A send with an unknown response is not automatically repeated; surface RenderUnknown and allow an explicit user refresh to choose a new operation.

If Telegram rendering succeeds but persistence fails, return `CommitUnknown` or `PersistenceUnavailable` with the action ID. A later reload reconciles persisted operation state. Never rerender automatically without checking whether the first operation already completed.

## 5. Input bindings

```python
bindings = InputBindings([
    CommandEntry("settings-command", command="settings", target="settings"),
    ReplyEntry("settings-reply", text_key="nav.settings", target="settings",
               from_nodes={"main"}),
    CallbackEntry("settings-inline", action="settings.open", target="settings"),
])
navigation.bind(bindings, translator=translator)
```

Commands use aiogram's command parser, including bot mentions and arguments. An application-supplied decoder validates arguments into node parameters. Do not implement commands by splitting arbitrary text at spaces.

Reply entries resolve localized labels for the active keyboard and allowed source nodes. Typed text equal to a button label is indistinguishable from a button press. Authorize both identically. Reject ambiguous translated labels within a scope; startup can validate known catalogs, with runtime checking for dynamic translations. Free-form typing states may disable reply navigation except explicit global actions.

Reply bindings match semantic entries, not emoji stripping or fuzzy labels. Track the locale of the installed keyboard so a language change can recognize the previous tray until it is replaced. Default policy: accept current and installed keyboard locale only, then refresh the tray.

Inline callbacks use compact opaque server-side tokens with short action codes, within Telegram's callback_data limit. A binding resolves token -> conversation, actor, session, view generation, action and validated parameters. Expired/stale controls are acknowledged. Markup cleanup requires tracked message ownership and a live coordination capability; a rejected or unknown token alone never authorizes stripping, since a partially sent prepared view can still be pending. Existing application callbacks can call `go()` without adopting the token codec.

Standalone input precedence: global command actions, scoped navigation bindings, business input handlers, fallback. When the optional idle integration is installed, its active prompt controls have explicitly configured precedence before these navigation bindings. Install through a dedicated router with documented inclusion order; do not steal arbitrary text before application filters. Both native bindings and user handlers execute the same authorization/action pipeline.

## 6. Persistence API and backend parity

```python
class NavigationRepository(Protocol):
    async def prepare(self, key: ConversationKey, *, expected_version: str | None,
                      intent: NavigationIntent) -> PreparedAction: ...
    async def checkpoint(self, key: ConversationKey, *, operation_id: str,
                         effect: EffectCheckpoint) -> None: ...
    async def lookup_operation(self, key: ConversationKey, *,
                               operation_id: str) -> ActionStatus: ...
    async def load(self, key: ConversationKey) -> VersionedSnapshot | None: ...
    async def commit(self, key: ConversationKey, *,
                     expected_version: str | None,
                     mutation: NavigationMutation) -> CommitResult: ...
    async def close(self) -> None: ...
```

`NavigationMutation` contains a stable operation ID, expected session ID, optional new location/view, accepted-activity flag and expiry intent. A commit completes the prepared operation, returning the new snapshot and CAS version; touch and track are explicit state-only intents. All methods check navigation session/view ownership and stable operation fingerprints. A pending external effect is never replayed merely because a CAS token changed. On conflict the caller reloads and revalidates; it must not replay business effects or a Telegram send blindly.

Memory uses one repository instance and asyncio isolation. Redis uses versioned records and conditional atomic commits. Both enforce expiry on read and mutation. Store wall timestamps for portability; use monotonic deadlines for in-process waiting. Memory is not safe across independent worker processes and loses state on restart.

The optional `aiogram_idle.integrations.nav` module exposes a repository projection implementing this protocol. It maps nav identity, snapshots and mutations to idle-owned activity contracts and an opaque integration component. It computes inherited policy selection in the adapter, then commits navigation and idle scheduling atomically in the idle backend. Its prepare/checkpoint/lookup methods map to idle operation primitives, not no-op wrappers. Idle-only CAS changes can cause a retry before effects; after rendering, the owning operation completes against its reservation rather than rerendering. Only this adapter imports both packages; neither core depends on the other. Do not run a standalone nav writer against the same integrated record. See the [storage design](storage-and-verification.md).

Persistence exceptions: `VersionConflict`, `SessionExpired`, `PersistenceUnavailable`, `CommitUnknown`, `SchemaUnsupported`. Domain exceptions: `NodeNotFound`, `InvalidParameters`, `AccessDenied`, `StaleView`, `UnsupportedContext`, `ConfigurationError`. Public errors carry safe identifiers, not tokens, Redis URLs or draft content.

## 7. Repository structure

```text
aiogram-nav/
  pyproject.toml
  README.md
  LICENSE
  CHANGELOG.md
  mkdocs.yml
  src/aiogram_nav/
    __init__.py
    py.typed
    models.py
    registry.py
    actions.py
    context.py
    navigation.py
    identity.py
    isolation.py
    errors.py
    events.py
    rendering/{base,text,delivery,cleanup}.py
    inputs/{bindings,reply,inline,commands,tokens}.py
    middleware/{context,activity}.py
    storage/{base,memory,redis,codec}.py
    storage/lua/{prepare,checkpoint,commit,token_consume}.lua
    effects.py
    recovery.py
  tests/{unit,contract,integration,typing}/
  examples/{reply_only,inline_only,commands_only,hybrid}/
  docs/{quickstart,concepts,public-api,storage,migration,security}.md
  .github/workflows/{ci,docs,publish}.yml
```

Keep individual source files below 500 lines. Redis modules import Redis only when the Redis backend is selected. No implicit environment-variable configuration in library imports.

## 8. Implementation work packages

| ID | Work | Dependency | Completion evidence |
| --- | --- | --- | --- |
| NAV-01 | Typed models, key normalization, errors and versioned codec | M0 review | Invalid identities/params rejected; JSON round trips and schema tests |
| NAV-02 | Registry, roots, targets, inheritance and migration validation | NAV-01 | Cycles/orphans/abstract targets rejected; generated tree snapshot |
| NAV-03 | Memory repository, prepare/checkpoint/complete ledger, expiry, history and action engine | NAV-01/02 | Contract tests, CAS conflicts, session recreation and back/cancel behavior |
| NAV-04 | Presenter contracts, text helper, partial-render recovery | NAV-03 | Reply/inline/hybrid API call traces and failure injection |
| NAV-05 | Commands, localized reply bindings, callback tokens | NAV-03/04 | Four interaction examples; actor/stale-token and ambiguous-label tests |
| NAV-06 | Dispatcher context, authorization and isolation adapters | NAV-03/05 | Real Dispatcher.feed_update tests with FSM enabled and disabled |
| NAV-07 | Redis repository and atomic token operations | NAV-03/06 | Real-Redis competing clients, restart, unknown-commit tests |
| NAV-08 | Migration recipe and tracking-only adapter | NAV-04/06 | Existing handlers track without duplicate sends or business draft changes |
| NAV-09 | Distribution, API docs and supported-version matrix | NAV-07/08 | Built wheel/sdist install; examples execute without source checkout |

## 9. Required tests and release gates

- Public API import/type tests, including installations without Redis.
- Registry property tests generate trees and invalid cycles/targets.
- Core repository contract suite runs against nav memory/Redis with aiogram-idle absent. Reuse it for the optional integration projection in the adapter test job, without making nav publication depend on that integration.
- Import/dependency checks prove nav never requires idle and idle core/Redis never requires nav.
- Private conversations remain isolated by bot and tenant; expired/recreated sessions reject old views.
- Reply-only navigation works without callback handlers; command-only works without keyboards; inline-only works without reply keyboards.
- Hybrid switching does not leave a Cancel tray permanently installed and does not resend a tray for every inline tab change.
- Free text, old localized labels, duplicate labels and command arguments follow documented precedence.
- Prepare failure causes no send; lost render response becomes RenderUnknown rather than automatic rerender.
- Rendering failure does not falsely commit a screen; persistence failure after rendering remains observable and recoverable.
- An application FSM draft survives Back; only its explicit cancellation hook can discard it. Continue preservation is an additional optional-idle integration test.
- Redis outage produces no local-memory fallback or unlocked protected action.
- At least 80% line coverage and explicit branch coverage for authorization, token ownership and CAS failure paths. Critical security paths require complete case coverage.

Publish nav 0.1 when its standalone interaction/backend matrix and applicable storage release gates pass. The optional idle adapter has separate release gates and is not a requirement for using or publishing standalone nav. Multi-panel stacks, a full widget framework and automatic business-form generation remain outside this release.

The combined integration uses only `integration.install(dispatcher, navigation=navigation)`, rather than installing either standalone middleware first. Staged Continue/restore rendering completes navigation and idle through one transaction and preserves the worker’s captured deadline claim. See aiogram-idle/docs/navigation.md.
