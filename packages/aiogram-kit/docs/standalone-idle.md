# Standalone aiogram-idle development recipe

The standalone memory and optional Redis implementation is available locally in the sibling `aiogram-idle` checkout. This recipe uses that local checkout and does not imply a PyPI release. The optional navigation integration is now available locally; see the recipe below.

## Install from the local checkout

In your bot's environment:

```bash
uv pip install -e /Users/armanavanesyan/oss/own/aiogram-idle
```

The core runtime requires aiogram 3 and does not require aiogram-nav or Redis. For the standalone Redis backend, install:

```bash
uv pip install -e '/Users/armanavanesyan/oss/own/aiogram-idle[redis]'
```

Import `RedisIdleBackend` from `aiogram_idle.storage.redis`, supply a caller-owned async Redis client and one stable prefix across replicas, and await `backend.initialize()` before use. Redis 7+ must be a writable standalone primary using `noeviction`. Redis remains authoritative with no memory fallback. Application drafts/FSM persistence remain application-owned; selecting Redis for idle does not persist a memory FSM. See the sibling package's `docs/redis.md` for lease, recovery and operational details. Kit does not yet declare dependency extras for this unpublished distribution.

## Run the examples

From the aiogram-idle checkout, set `BOT_TOKEN` in your environment and run:

```bash
uv sync --frozen --python 3.12
uv run --no-sync python examples/demo.py --controls reply
```

Other supported demo switches are `--controls inline`, `--controls commands`, `--controls hybrid` and `--fsm`. `/draft` starts an application-owned sample draft; accepted text resets inactivity. Continue resumes it, while Cancel or grace expiry invokes the application's cleanup and restoration adapters. `/status` reports safe lifecycle metadata.

The demo deliberately enables creation and uses short test intervals. Library configuration defaults to disabled. Memory state and recovery evidence disappear on process restart; run only one process against a memory backend.

## Integration boundary

Standalone idle uses opaque activity keys, explicit policy IDs, session/activity guards and application adapters. It needs no registry, node IDs or root screen. Applications retain ownership of drafts, authorization, translations and final UI.

The optional navigation adapter is described in the [design plan](design/aiogram-idle.md), not installed by this recipe. The [storage contract](design/storage-and-verification.md) distinguishes in-process recovery from Redis durability. Do not infer implemented capabilities from the full roadmap.

The Redis concurrency audit adds immutable storage-profile checks and atomic namespace/configuration-loss detection. Configure Redis FSM storage with `DefaultKeyBuilder(with_bot_id=True)` and keep its isolation unchanged after installing idle. Unknown business-effect ledgers require explicit recovery; normal activity must not erase them. The sibling `aiogram-idle/docs/redis-audit.md` records the contracts and verification. The optional navigation integration is now available locally; see the recipe below.


The optional navigation adapter is now available locally:

```sh
uv pip install /Users/armanavanesyan/oss/own/aiogram-nav
uv pip install '/Users/armanavanesyan/oss/own/aiogram-idle[nav,redis]'
```

Use `aiogram_idle.integrations.nav.NavigationIntegration` and `NodePolicies`, then
install only the combined integration. It commits navigation/activity/deadline
updates atomically and shares one coordinator across handlers and workers.
See the sibling package’s docs/navigation.md and examples/navigation.py for all
four control styles, memory/Redis usage, recovery and external-business-store
limits. Kit adds no dependency extra until compatible distributions are published.
