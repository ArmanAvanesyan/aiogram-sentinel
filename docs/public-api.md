# Public API

The standalone package owns its contracts. No navigation model imports idle types.

| API | Responsibility |
| --- | --- |
| `ConversationKey` | Private actor-owned identity including namespace, bot and optional tenant |
| `Node`, `NavigationRegistry` | Stable nodes, explicit parents/targets, parameter validation and migrations |
| `NavigationConfig` | Session/recovery intervals and bounded history, records, tokens and receipts |
| `Navigation`, `NavigationContext` | Authorized action preparation, rendering, completion and tracking |
| `NavigationRepository` | Storage CAS, operation receipts, checkpoints and callback tokens |
| `MemoryNavigationRepository` | Single-process implementation with an injected clock and shared coordinator |
| `TextPresenter`, `ScreenSpec` | Restricted text/keyboard plans and recorded Telegram effects |
| `InputBindings` | Explicit command, localized reply and callback entry declarations |

## Context methods

Handlers receive `nav_context`. `current()` returns the committed snapshot or
`None`. The convenience actions are `go(node_id, params=...)`, `back()`, `home()`,
`cancel()` and `refresh()`. Each accepts an `operation_id` override. Direct callers
must provide stable IDs; update contexts derive stable substep IDs automatically.

`touch(source=...)` records accepted input without changing the displayed screen.
`track(node_id, params=..., rendered=...)` adopts an already-rendered view without
sending it again. For stronger recovery, call `prepare_render()` before external
delivery and `complete_render()` with its receipt afterward.

`RenderResult` identifies the prepared view and its message references, locale and
reply keyboard semantic key. `RenderRequest` supplies the reserved operation,
session/view identity, target node, validated parameters, current snapshot, Bot,
application dependency scope and stage recorder.

## Presenters and bindings

`TextPresenter` maps renderer names to asynchronous application functions taking a
`RenderRequest` and returning a `ScreenSpec`. A spec can contain inline markup,
reply markup, both, or neither. Reply markup requires a semantic keyboard key.
Removing a reply keyboard uses explicit `ReplyKeyboardRemove`; omission keeps it.

`CommandEntry`, `ReplyEntry` and `CallbackEntry` declare stable entry IDs, targets or
actions and optional source-node scopes. Commands use aiogram's parser, including
bot mentions and argument decoders. Reply entries resolve semantic translation
keys in current and installed tray locales. Colliding labels fail validation.

Use `inputs.tokens.prepare_token()` during prepared rendering to reserve an opaque
callback before sending. Supply the registered callback entry ID, session and view
identity, action, expiry and stable substep ID. Do not embed draft values in
callback data.

## Errors

Public failures distinguish invalid parameters, access denial, unknown nodes,
stale views/sessions, CAS conflicts, operation-ID conflicts, unsupported context,
storage failure and uncertain rendering. An unknown external result is not a
retry instruction. Lookup and recovery must inspect its existing operation before
performing another effect. Error messages carry safe identifiers rather than draft
content or credentials.

## Optional Redis repository

Import `RedisNavigationRepository` from `aiogram_nav.storage.redis`. Construct it
with a caller-owned `redis` client, optional `prefix` and `NavigationConfig`, then
`await initialize()`, or use `await RedisNavigationRepository.from_url(url, ...)`.
It implements the same repository protocol as memory, including prepared actions,
effect checkpoints, operation lookup, token reservation/consumption and bounded
`sweep(limit=100)`. `close()` closes only a URL-owned client and requires drained
coordination scopes. See [Redis operational requirements](redis.md).

`BackendInconsistent` distinguishes a server-side transaction error from a transport
response with unknown outcome (`CommitUnknown`). Both require inspection before
new external effects. `SchemaUnsupported` rejects malformed or newer persisted
records. No Redis failure returns a successful local-memory result.

Custom presenters must call `CleanupRequest.ensure_owned()` when supplied, immediately before each new cleanup effect. Invalid/stale callbacks are acknowledged without deleting unproven message markup; committed-view cleanup uses tracked references.

## Application ownership additions in 0.2

- `create_bindings_router(navigation)` plus explicit manual `install` options.
- `ApplicationPresenter(cleanup=..., render=None)` and `prepare_action`/`complete_render`.
- Shared `SessionAuthority`, `ExternalSession` and `TrackedEventIsolation` contracts.
- `callback_rejection` with a public `CallbackRejection` value and coarse reason.
- `drain(timeout_seconds=10)` before resource closure.
- `RedisDeploymentAttestation` and explicit repository storage-format activation.

[Application ownership](application-integration.md) defines the guarantees and
required callback responsibilities; [migration](migration.md) covers activation.

## Optimized storage and deterministic engines

`EngineName` is `Literal["python", "rust"]`; `NavigationConfig(engine=...)` is keyword
only. Direct backends accept the same option, and fresh backends can opt into
`storage_format=3` explicitly. See [performance and engines](performance-and-engines.md)
for activation, finite replay retention, physical receipt TTL and native release gates.

`AtomicAdoptionRepository.adopt_render(key, *, expected_version, intent, rendered,
coordination_scope=None)` is optional. `track()` selects it before mutation when
supported; failed adoption never falls back to another sequence or engine.

Optional component hosts use `LedgerRead.from_payload()`/`to_payload()`,
`LedgerDelta.to_payload()` and `NavigationLedgerReducer`. The reducer exposes a
bounded memory `repository`, detached `integration_payload(operation_id)`,
`set_integration_payload()`, an owned `record` view, validated `replace_record()` and
`delta()`. Canonical terminal results are immutable; only their control receipt
updates and first opaque integration result can be added under the same fence.
No host should duplicate canonical navigation history in its own action receipts.
