# aiogram-idle

Source development and releases are maintained in the [aiogram-kit monorepo](https://github.com/ArmanAvanesyan/aiogram-kit). See the [workspace contributing guide](https://github.com/ArmanAvanesyan/aiogram-kit/blob/main/CONTRIBUTING.md); package examples live under `packages/aiogram-idle/`.

Standalone inactivity policies for aiogram 3, with typed session/activity contracts and memory or optional Redis storage. Add Continue/Cancel questions or quiet cleanup to ordinary handlers and FSM conversations without adopting a navigation framework.

Version `0.3.1` supports Python 3.10+ and aiogram 3.22 or newer within the 3.x series.

## Compatibility

| Component | Supported / tested |
| --- | --- |
| Python | 3.10–3.14 in CI |
| aiogram | 3.22.0 minimum; latest resolvable 3.x |
| Redis server | 7 and 8, single writable primary, noeviction |
| redis-py extra | >=5.0.8,<8; minimum/current in CI |
| aiogram-coordination | >=0.1.0,<0.2; required, Redis optional |
| aiogram-nav extra | >=0.3.0,<0.4; never installed by the base package |

Minimum aiogram is tested on Python 3.10–3.13; Python 3.14 uses current
aiogram because historical dependency wheels do not support it.
See [testing](docs/testing.md) for actual local evidence versus configured CI.

## Format 3 and optional native engine

Version 0.3 adds explicit `storage_format=3` for fresh backends, individual Redis
receipt TTLs, bounded recovery and a canonical optional navigation ledger. Existing
namespaces require drained, verified migration. Python remains the default engine;
Rust is an explicitly selected, separately built companion with no runtime fallback.
See [migration, replay retention and engine selection](docs/migration-0.3.md).
The recorded 0.3.0 native CPU gate failed (Rust used about 6.6% more CPU on the selected
representative workload). The native companion remains source-only: no native PyPI
release, tag or extra is provided. Keep the default Python engine.

## Application-owned integration in 0.2

Use `ActivityRegistration` and `idle_context.activate(...)` to enter a flow
without constructing snapshots. An optional read-only `SessionAuthority`
binds activity to an existing application session after explicit storage-format
activation. Public tracked isolation supports verified application locks without
replacing FSM storage. The [application integration guide](docs/application-integration.md)
and [0.2 migration](docs/migration-0.2.md) explain setup, authority failures,
manual navigation routing and staged activation.

## Install

```bash
python -m pip install aiogram-idle==0.3.1
# Optional standalone Redis backend:
python -m pip install 'aiogram-idle[redis]==0.3.1'
# Optional navigation integration, with or without Redis:
python -m pip install 'aiogram-idle[nav]==0.3.1'
python -m pip install 'aiogram-idle[nav,redis]==0.3.1'
```

The core runtime dependency is aiogram 3. Redis and aiogram-nav are not installed
by the base package. The Redis backend requires Redis 7 or newer.

See [Redis setup and recovery](docs/redis.md). The optional [aiogram-nav integration](docs/navigation.md) is available through `[nav]` or `[nav,redis]`; neither base nor Redis-only installs require navigation.

## Run the examples

Clone the repository to run its examples, install the frozen development
requirements with `uv sync --frozen --python 3.12`, then set `BOT_TOKEN` in your
environment and choose the prompt controls:

```bash
uv run --no-sync python examples/demo.py --controls reply
uv run --no-sync python examples/demo.py --controls inline
uv run --no-sync python examples/demo.py --controls commands
uv run --no-sync python examples/demo.py --controls hybrid
uv run --no-sync python examples/demo.py --controls inline --fsm
```

`/draft` starts the sample activity. Accepted text updates its draft and resets inactivity. After the configured delay, the bot asks whether to continue. Continue preserves the draft; Cancel or grace expiry runs the application's abandonment and restoration adapters. `/status` reports safe current lifecycle state. Use `--after` and `--grace` to adjust the demonstration intervals.

The examples configure safe debug logging and read the token only from the environment. They send real Telegram messages when run with a token; automated tests use a fake bot session instead.

## How it fits

1. Define named `ExemptPolicy`, `PromptPolicy` or `QuietRestorePolicy` values.
2. Supply application `inspect`, `resume`, `abandon` and `restore` adapters.
3. Construct `IdleRuntime` with `MemoryIdleBackend` or `RedisIdleBackend` and a presenter.
4. Install its context middleware and controls on a dispatcher.
5. Explicitly enter an activity or touch it after accepted input.

Activity keys are opaque application labels, not navigation nodes. Draft storage and business rules stay in the application. Inactivity creation is disabled by default; examples explicitly enable it.

See [the standalone guide](docs/standalone.md) for contracts and integration details, and [failure semantics](docs/recovery.md) for the recovery boundaries.

## Guarantees and limits

- Memory storage is for one event loop in one process and loses all state, deadlines and recovery receipts on restart.
- Generation guards and conditional transitions protect current activity state. They do not create a transaction with an application database or Telegram.
- Explicit operation IDs identify logical substeps. Reusing one ID with different inputs is an error.
- Inline controls bind to a prompt generation. Reply text and bare commands resolve only the current authorized prompt and cannot identify an older originating prompt.
- Unknown Telegram responses are not blindly resent by default. A lease cannot retract an already in-flight request.
- Silent Telegram messages can still notify without sound.
- Redis storage supports coordinated multi-process workers on a standalone writable primary with `noeviction`. Infrastructure persistence and replication determine durability; there is no memory fallback.
- Private chats are the initial supported presentation context. The optional navigation adapter is available separately. External session stores, Redis Cluster and a durable analytics outbox remain deferred.

See the [Redis concurrency and FSM audit](docs/redis-audit.md) for the latest corrected failure paths, and the [memory audit](docs/audit.md) for adapter replay requirements.

## Development

```bash
uv sync --frozen --extra redis
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
AIOGRAM_IDLE_REDIS_URL=redis://localhost:6379/0 AIOGRAM_IDLE_REQUIRE_REDIS=1 uv run --no-sync pytest --cov=aiogram_idle --cov-report=term-missing
uv build
uv run --no-sync twine check dist/*
```

CI tests Python 3.10–3.14 with the latest resolvable aiogram 3 release, and aiogram 3.22.0 on Python 3.10–3.13. The minimum aiogram endpoint pins dependencies predating Python 3.14 support, so that combination is excluded. CI then builds and installs artifacts in clean environments. It has no publishing or deployment step.

See [local verification results](docs/verification.md) for the tested matrix and deferred capabilities.

See [installation](docs/installation.md), [API contracts](docs/api.md),
[architecture](docs/architecture.md) and [testing](docs/testing.md) for contributor
guidance. CI also requires strict documentation and security checks and runs a
separate optional-navigation job; standalone jobs remain navigation-free.
Dependency auditing uses Python 3.11+; CI uses 3.12.

Read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and the
[code of conduct](CODE_OF_CONDUCT.md). Maintainers use
[the release checklist](docs/releasing.md); a repository push does not publish.

## License

MIT. See [LICENSE](LICENSE).

For a source checkout, use `uv sync --frozen` and `uv run --no-sync ...`. Selecting the nav extra resolves published dependencies; adjacent peer checkouts are not required. See [installation](docs/installation.md) for explicit joint-development overrides.
