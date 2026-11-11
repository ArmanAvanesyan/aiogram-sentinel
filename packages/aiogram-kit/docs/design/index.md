# Navigation and idle package implementation programme

Status: reviewed programme, 10 November 2026. The documents include planned milestones beyond the local implementations described below.

Implementation status: the standalone memory and optional Redis aiogram-idle package is implemented locally at `/Users/armanavanesyan/oss/own/aiogram-idle`, with guarded contracts, lifecycle/worker, Telegram controls, examples and automated tests. See the [standalone installation recipe](../standalone-idle.md). Redis includes real-server concurrency, lease and crash-recovery tests. Optional navigation integration is implemented locally with memory and real-Redis tests; publication remains deferred. The full design includes milestones beyond these implementations.

Navigation implementation status: standalone aiogram-nav memory/Redis contracts, rendering, all four input styles and FSM integration are implemented locally at `/Users/armanavanesyan/oss/own/aiogram-nav`. See the [navigation recipe](../standalone-nav.md). Redis navigation now has real-server parity, crash-recovery and FSM tests. The optional combined adapter is now implemented locally in aiogram-idle with a separate memory/Redis test matrix; publication and Kit dependency extras remain deferred.

Build two independently installable packages: `aiogram-nav` for navigation and `aiogram-idle` for inactivity handling. Each library supports reply keyboards, inline keyboards, commands and hybrids. Idle works with ordinary handlers or FSMs without any navigation registry; an optional adapter connects the two libraries. Both packages support memory and optional Redis backends. `aiogram-kit` provides installation extras and integration documentation.

## Documents

1. [aiogram-nav design and implementation plan](aiogram-nav.md): navigation semantics, public APIs, presentation, input routing, persistence, repository layout and work packages.
2. [aiogram-idle design and implementation plan](aiogram-idle.md): policies, prompt transports, lifecycle, public APIs, runtime integration and work packages.
3. [Storage, failure handling and verification](storage-and-verification.md): identity mapping, atomic Redis operations, claims, ambiguity, expiry, testing and release gates.
4. [Pre-implementation design review](review.md): corrected contradictions and the acceptance cases added by review.

The storage document is part of both package specifications. Its safety requirements take precedence over shorthand examples.

## Package ownership and dependency direction

| Package | Owns | Depends on |
| --- | --- | --- |
| aiogram-nav | Node registry, location, navigation actions, presentation contracts, input bindings, navigation repository protocol | aiogram |
| aiogram-idle | Activity/conversation contracts, idle policies, lifecycle, prompt controls, deadline worker, memory/Redis backends | aiogram; aiogram-nav only through the optional nav extra |
| aiogram-sentinel | Incoming-update rate limiting, debouncing and error middleware | Existing dependencies |
| aiogram-cmds | Telegram command definitions, localization, profiles and scopes | Existing dependencies |
| aiogram-kit | Extras, suite compatibility matrix, recipes and suite integration tests | Selected packages through extras |

`aiogram-nav` and the `aiogram-idle` core do not import each other. Both install and run independently. `aiogram-idle[nav]` supplies an optional integration module that imports both packages. Its registry inheritance, screen reconstruction and atomic navigation projection are adapter responsibilities. No new general-purpose shared-core package is needed.

The application owns business drafts, permissions, feature flags, translations, tenant timezone selection and analytics delivery. A screen renderer and flow adapter receive application dependencies explicitly.

## Supported interaction styles

| Style | Entry and navigation | Continue and Cancel | Important constraint |
| --- | --- | --- | --- |
| Reply only | Localized button text and application text filters | Temporary localized reply keyboard | Text carries no prompt generation; validate against current server-side state |
| Inline only | Compact callback tokens | Inline prompt controls | Bind controls to actor, conversation, generation and current view |
| Commands only | aiogram Command filters | `/continue` and `/cancel` | Commands have no originating prompt ID; resolve only the current authorized prompt |
| Hybrid | Any supported combination per screen | Independently selected prompt transport | Inline controls and reply keyboards require separate messages when both must change |

All four modes are first-release acceptance requirements. A bot does not have to adopt inline keyboards to use either package.

The first release supports private-chat presentation and workers. Identity and pure registry APIs accommodate aiogram topic and business dimensions, but group/shared reply-keyboard UX, channel delivery, business-message behavior and Telegram inline-mode messages are not advertised as supported until dedicated adapters and tests exist. Unsupported contexts produce a clear error, rather than silently sharing another user's state.

## aiogram-kit integration

Keep `pip install aiogram-kit` lightweight. Add these extras after dependent distributions have been published and verified:

```text
aiogram-kit[nav]
aiogram-kit[idle]
aiogram-kit[navigation-idle]
aiogram-kit[redis]
aiogram-kit[all]
```

| Extra | Dependency selection |
| --- | --- |
| nav | aiogram-nav in the suite-tested compatible range; does not install idle |
| idle | aiogram-idle in the suite-tested range; does not install nav |
| navigation-idle | aiogram-nav and aiogram-idle[nav] in suite-tested ranges |
| redis | aiogram-nav[redis] and aiogram-idle[nav,redis] in tested ranges |
| all | Combined navigation-idle bundle, Redis extras, sentinel and cmds in tested ranges |

Document that `redis` installs the navigation/idle suite with Redis support; it does not select a backend at runtime. Backend construction remains explicit. Selecting `[nav,idle]` installs both independent packages but does not enable their adapter; use `[navigation-idle]` for the combined recipe. Direct `aiogram-idle[redis]` installs Redis support without navigation. Avoid further combinatorial extras.

Keep imports owned by their packages:

```python
from aiogram_nav import Navigation, NavigationRegistry
from aiogram_idle import IdleRuntime, PromptPolicy
```

Do not re-export every symbol under `aiogram_kit`. Kit initially has no global setup singleton and does not rewrite dispatcher middleware or command menus.

Provide runnable recipes for all interaction styles with both backends. Provide standalone-idle recipes with ordinary handlers/FSMs, standalone-nav recipes and combined recipes. Only combined recipes require a registry. Keep identity, policy and adapter behavior comparable across backends. Include existing-handler migration, FSM coexistence, Sentinel integration and Cmds integration.

### Middleware and lifecycle integration

1. Resolve bot, tenant, user and conversation identity.
2. Apply authentication and the application's accepted-activity rules.
3. Use one shared isolation owner for update handlers and background idle work.
4. Load runtime context; let route bindings and application handlers dispatch actions.
5. Commit accepted activity through the idle backend, navigation through its repository, or both through the optional atomic integration.
6. Emit observational hooks only after the corresponding commit.

Actual outer/inner middleware placement must be verified against the supported aiogram versions. The sequence above specifies semantics, not an instruction to nest an extra non-reentrant lock inside aiogram's existing FSM isolation.

Sentinel remains input protection. Updates it rejects do not count as accepted idle or navigation activity. Ensure its callback debounce does not consume valid idle controls without acknowledgement. Changes to an existing Sentinel middleware chain require its own explicit configuration; Kit must not clear another package's middlewares.

Cmds may advertise `/menu`, `/back`, `/continue` and `/cancel`, but the selected nav/idle routers bind and authorize these commands independently. A visible command is not authorization. Kit examples register each handler exactly once. Dynamic command visibility and BotCommandScope updates do not create navigation nodes.

Register startup and shutdown idempotently. User-supplied Redis clients stay caller-owned. Stop idle claiming, drain bounded work, persist safe recovery state and then close package-owned clients. Double setup on the same dispatcher raises a configuration error.

## Compatibility and distribution policy

- Proposed Python baseline: 3.10+, matching the current suite. Test each advertised interpreter version; use a compatibility timeout helper on Python 3.10 rather than unconditionally calling `asyncio.timeout`.
- aiogram 3 only. Establish the minimum supported minor from executable API tests; do not claim compatibility with every 3.x release merely from an unbounded dependency declaration.
- Redis support is optional. Memory installations must import and run without the Redis package installed.
- Redis initial support: standalone primary, including a primary managed by Redis Sentinel with reconnect support; this is unrelated to aiogram-sentinel. Redis Cluster is deferred and rejected by the initial backend.
- Do not claim recovery from Redis data loss. Persistence, replication and failover configuration determine infrastructure durability.
- Publish typed packages with `py.typed`, an sdist, a wheel, an MIT license and package-specific changelogs.
- Proposed first versions: 0.1.0. Treat public API changes deliberately; avoid promising a stable 1.0 before integrated field validation.
- PyPI package names are working names until registration succeeds. Name availability is not a design dependency.

## Cross-repository implementation order

| Milestone | Deliverables | Depends on | Exit criteria |
| --- | --- | --- | --- |
| M0 Contracts | Independent nav/idle identity and storage contracts, idle activity API, adapter mapping and ADRs | These designs | Neither core needs the other; review session guards, effect recording, lock leases and configuration generations |
| M1 Nav memory | Nav registry, actions, four input styles, presentation, memory repository | M0 | All memory navigation examples execute, including prepared-render recovery; public API tests pass |
| M2 Nav Redis | CAS persistence, isolation integration, versioned serialization | M1 | Real-Redis concurrency and restart tests pass |
| M3 Idle memory | Standalone activity API, policies, lifecycle, four prompt styles, deterministic worker | M0 | Runs without aiogram-nav; fake-clock lifecycle and control tests pass |
| M4 Idle Redis | Standalone idle backend, atomic scheduling, lease recovery, operation ledger | M3 | Multi-process crash, unknown-effect and live-index recovery tests pass with aiogram-nav absent |
| M5 Optional integration | Nav adapter, inherited node-policy mapping, atomic projection, neutral examples | M2, M4 | Combined tests pass; standalone installations remain independent |
| M6 Distribution | Independent package candidates, optional adapter, Kit extras and compatibility matrix | Relevant package milestones; M5 for combined bundle | Clean-install and dependency-isolation tests pass |

Navigation milestones M1/M2 and idle milestones M3/M4 are independent after M0. Neither standalone release is blocked by M5 or access to any specific consuming project. Work estimates should be assigned after M0; do not turn these milestones into calendar commitments without staffing and pilot access.

## Consumer adoption recipes

Standalone idle: map accepted handler/FSM activity to an opaque activity key and named policy, supply resume/abandon/restore adapters, install the selected backend and worker disabled, then enable in a test environment. No screen registry, root or node ID is required.

Standalone navigation: declare a registry and renderers, track successful screens and bind the desired inputs. No idle worker is installed.

Combined: install the optional nav integration, map registry nodes to idle policies, use its atomic repository projection, then validate inherited policies and control routing before enablement.

For all recipes, validate translations and iOS, Android and Desktop UX, exercise failure recovery, and enable application telemetry separately. A silent message can still notify without sound.

### Illustrative consuming-project example

A bot might prompt for an unfinished feedback draft, quietly restore settings UI, and exempt read-only panels or an independently expiring sign-in attempt. These are sample application choices, not built-in flow names, mandatory policies, release dependencies or acceptance criteria.

Rollback disables new prompts while continuing to handle existing Continue/Cancel controls and grace expiry. Standalone activity/policy migrations must preserve or map active identities. For the optional nav integration, registry migrations must also preserve or map persisted node IDs. Never remove callback decoding support while active prompts still use that version.

## Decisions fixed by this proposal

- Stable string IDs; documentation numbers are derived.
- Structural parents are explicit; transition edges and history are separate.
- No mandatory inline UI or FSM takeover.
- Memory and Redis share semantic contracts, with different durability guarantees.
- Idle owns activity and scheduling atomically without navigation. The optional nav adapter adds atomic navigation-and-idle commits.
- Unknown Telegram send outcomes default to no automatic resend.
- No automatic Redis-to-memory failover.
- No exactly-once Telegram delivery claim.

## Decisions that require pilot evidence

Choose per application: accepted free-text behavior while prompted, quiet-hours resolver, reply-label handling after language changes, and retry policy for ambiguous Telegram sends. The libraries supply explicit defaults and configuration; none may be decided implicitly from incoming text or the host timezone.

## References

- [aiogram FSM storage and identity](https://docs.aiogram.dev/en/latest/_modules/aiogram/fsm/storage/base.html)
- [aiogram Redis event isolation](https://docs.aiogram.dev/en/latest/_modules/aiogram/fsm/storage/redis.html)
- [Telegram reply and inline keyboard contracts](https://core.telegram.org/bots/api#replykeyboardmarkup)
- [Redis transactions and optimistic concurrency](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Redis distributed locking guidance](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)
- [aiogram-dialog transitions for comparison](https://aiogram-dialog.readthedocs.io/en/2.3.0/transitions/)
