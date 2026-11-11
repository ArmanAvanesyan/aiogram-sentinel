# Standalone aiogram-idle

Install Idle independently from PyPI:

```sh
uv pip install 'aiogram-idle==0.3.1'
```

Python 3.10+ and aiogram 3.22+ within 3.x are required. The core installation
includes neither Redis nor aiogram-nav. The `aiogram-kit` distribution remains
lightweight; install each library directly.

## Optional storage and navigation

```sh
uv pip install 'aiogram-idle[redis]==0.3.1'
# Only when navigation is needed:
uv pip install 'aiogram-idle[nav,redis]==0.3.1'
```

Supply a caller-owned async Redis client to
`aiogram_idle.storage.redis.RedisIdleBackend`, use a stable prefix across replicas,
and await `backend.initialize()`. Redis 7+ must be a writable standalone primary
using `noeviction`. Application drafts and FSM persistence remain application-owned;
Redis idle storage does not persist a memory FSM. There is no automatic memory
fallback after a Redis failure. See the [Redis guide](libraries/aiogram-idle/docs/redis.md).

Standalone Idle uses opaque activity keys, policy IDs, session/activity guards and
application adapters. It needs no navigation registry, node IDs or root screen.
Applications own authorization, translations, drafts and final UI. Creation is
explicitly disabled by default. Memory state and recovery evidence disappear on
restart; use one process with a memory backend.

## Runnable examples and development

Clone the monorepo and run the maintained example:

```sh
git clone https://github.com/ArmanAvanesyan/aiogram-kit.git
cd aiogram-kit
uv sync --frozen --all-packages --all-groups --all-extras
# Export BOT_TOKEN in your environment first.
uv run --no-sync python packages/aiogram-idle/examples/demo.py --controls reply
```

Other controls are `inline`, `commands` and `hybrid`; add `--fsm` for the FSM example.
`/draft` starts an application-owned sample draft, and accepted text resets inactivity.
Continue resumes it; Cancel or grace expiry invokes application cleanup and restoration.
The example enables short test intervals and safe debug logging explicitly.

For app-owned sessions and isolation, see the
[coordination guide](libraries/aiogram-coordination/README.md) and
[external-session example](https://github.com/ArmanAvanesyan/aiogram-kit/blob/main/packages/aiogram-idle/examples/external_sessions.py).

## Optional combined integration

Use `aiogram_idle.integrations.nav.NavigationIntegration` and `NodePolicies`.
Construct Navigation with `integration.navigation_repository` and call only
`integration.install`, rather than installing the two components separately.
Navigation/activity/deadline updates share one atomic backend transaction and one
coordinator. Telegram sends, application business stores and FSM data are outside
that transaction. Unknown effects require explicit recovery; normal activity must
not erase unresolved recovery evidence.

See the [integration contract](libraries/aiogram-idle/docs/navigation.md) and
[example](https://github.com/ArmanAvanesyan/aiogram-kit/blob/main/packages/aiogram-idle/examples/navigation.py).
The original design records remain preserved under `packages/aiogram-kit/docs/`;
implementation guides describe the supported release.
