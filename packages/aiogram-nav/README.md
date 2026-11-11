# aiogram-nav

Standalone screen navigation for aiogram 3, with a typed registry, memory or Redis
repositories, prepared rendering and explicit input bindings. Use reply keyboards,
inline controls, commands or hybrids without adopting an idle framework.

Version 0.3.0 is an initial alpha release. Review the recovery and storage
boundaries before adopting it in an application.

## Install

Requires Python 3.10+ and aiogram 3.22 or newer within the 3.x series.

```sh
pip install aiogram-nav==0.3.0
# Optional persistent storage:
pip install 'aiogram-nav[redis]==0.3.0'
```

The runtime depends on aiogram and aiogram-coordination; it never imports Idle. Neither aiogram-idle nor Redis is required.
See [Redis setup and recovery](docs/redis.md) and [format-three storage and engines](docs/performance-and-engines.md). Contributors can install an editable
checkout with `uv sync --extra redis`; see [CONTRIBUTING.md](CONTRIBUTING.md).

Redis hot-path improvements require **format three**: choose `storage_format=3`
for a fresh namespace, or explicitly migrate after draining old workers. Default
startup remains compatible with formats one/two and retains their whole-record
storage; installing 0.3.0 alone does not upgrade an existing Redis namespace.

## Run a demonstration

Clone the repository for its runnable examples, then set `BOT_TOKEN` in the environment:

```sh
git clone https://github.com/ArmanAvanesyan/aiogram-nav.git
cd aiogram-nav
uv sync --python 3.12
uv run python examples/demo.py --style reply
uv run python examples/demo.py --style inline
uv run python examples/demo.py --style commands
uv run python examples/demo.py --style hybrid --fsm
```

`/start` opens a neutral example menu. Back preserves application drafts; Cancel
uses an explicit application hook to discard only owned draft fields. The examples
configure debug logging and never configure logging globally inside the library.
CLI help runs without a token. Tests use a recording Telegram transport.

## Core behavior

- Register stable node IDs, structural parents, explicit Back/Cancel targets,
  validators and renderer keys. Authorization runs through one action pipeline.
- `go`, `back`, `home`, `cancel` and `refresh` prepare an operation before effects.
  The previous screen remains current until rendering and completion succeed.
- Stage receipts retain partial renders. Confirmed effects can be recovered;
  unknown sends are not repeated automatically. Explicit refresh can select a
  new presentation operation, while unknown business cancellation stays guarded.
- `track` adopts an existing successful render. For recoverable application screen
  helpers, use `prepare_render` before sending and `complete_render` afterward.
- Accepted activity is explicit through navigation actions or `touch`; background
  renders can preserve the activity clock. Absolute session expiry never slides.
- Opaque callbacks bind actor, conversation, session and view. Localized reply
  text and bare commands act on current state and cannot prove an old origin.
- Dispatcher middleware protects the whole handler and shares verified FSM
  isolation. Automatic installation puts bindings before business routers. Manual
  installation keeps the application's chosen router order; intentional Dispatcher
  root handlers require `allow_root_handlers=True`.

See [quickstart](docs/quickstart.md), [public API](docs/public-api.md),
[migration](docs/migration.md), [storage](docs/storage.md) and
[verification](docs/verification.md). The [memory audit](docs/memory-audit.md) records
concurrency, callback and FSM review corrections.

## Boundaries

Memory storage supports one event loop/process and loses everything on restart.
Application FSM state, authorization and business drafts remain application-owned.
A stage recorder cannot make Telegram and a database transactional.

The optional navigation/idle adapter lives in
`aiogram_idle.integrations.nav`; adopting it is explicit and does not add an idle
dependency to this package. See [optional integration](docs/idle-integration.md).
Multiple simultaneous panels and durable analytics remain deferred.

## Development

```sh
uv sync --extra redis
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright src examples
uv run --no-sync pytest
# Full coverage including real Redis (see docs/redis.md):
AIOGRAM_NAV_REDIS_URL=redis://localhost:6379/0 AIOGRAM_NAV_REQUIRE_REDIS=1 uv run --extra redis pytest --cov=aiogram_nav --cov-report=term-missing
uv run --no-sync mkdocs build --strict
uv build
uv run --no-sync twine check dist/*
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for repository conventions and verification,
[SECURITY.md](SECURITY.md) for vulnerability reporting, and
[release guidance](docs/releasing.md) for maintainer procedures.

MIT licensed. See [LICENSE](LICENSE).

## Application ownership and compatibility

See [application-owned integration](docs/application-integration.md) for custom FSM
isolation, manual router placement, prepared rendering, external session authority
and bounded draining. These are explicit opt-ins; automatic routing and owned
sessions retain their existing defaults.

| Target | Required checks |
| --- | --- |
| Python | 3.10, 3.11, 3.12, 3.13, 3.14 |
| aiogram | 3.22 minimum and latest 3.x; minimum on Python 3.14 excluded for upstream wheel compatibility |
| Redis server | 7+ single primary, non-cluster, noeviction; real-server CI |
| redis-py | 5.0.8 minimum and latest below 8 |
| Coordination | >=0.1.0,<0.2 |

Configured matrices and locally executed checks are distinguished in release verification.
