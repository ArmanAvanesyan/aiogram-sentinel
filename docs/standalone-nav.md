# Standalone aiogram-nav development recipe

The standalone navigation package is implemented in the sibling
`aiogram-nav` checkout. This is a local unpublished distribution.

```sh
uv pip install -e /Users/armanavanesyan/oss/own/aiogram-nav
```

It requires aiogram 3.22+ within 3.x and Python 3.10+. It does not require
aiogram-idle or Redis. Kit dependency extras remain deferred until usable
published distributions and tested version ranges are available.

From the navigation checkout, set BOT_TOKEN in the environment and run:

```sh
uv sync --python 3.12
uv run python examples/demo.py --style reply
uv run python examples/demo.py --style inline
uv run python examples/demo.py --style commands
uv run python examples/demo.py --style hybrid --fsm
```

The library registers explicit screens and input bindings, prepares rendering
before network effects, and commits location only after completion. It retains
partial/unknown rendering evidence rather than automatically resending it.
Back preserves business drafts. Cancel invokes an explicit application hook;
navigation never clears arbitrary FSM fields.

Install navigation before including business Routers. When bindings are enabled,
Dispatcher root handlers would outrank the binding router and are rejected.
Verified SimpleEventIsolation is shared with direct navigation actions;
disabled FSM isolation uses the package's full-handler coordinator.

Memory state is single-process, bounded and lost on restart. Redis navigation
storage is available as the standalone package’s `redis` extra. The optional idle adapter is now implemented in the sibling aiogram-idle checkout. The packages are independent:
using navigation does not start an idle worker, and idle does not require a tree.
See the sibling package's docs/verification.md for test evidence and limits.

For an application-owned Redis FSM store, use DefaultKeyBuilder(with_bot_id=True); known builders that alias bot identities are rejected even when navigation storage is memory.

The standalone memory audit now verifies shared effect-stage execution, partial-receipt truth, callback ownership and unchanged FSM/storage/router mapping. Destination authorization does not replace cancellation-hook business authorization. See the sibling package's docs/memory-audit.md for corrections and current verification; Redis storage now has a separate real-server verification suite.

For persisted navigation across processes:

```sh
uv pip install -e '/Users/armanavanesyan/oss/own/aiogram-nav[redis]'
```

Use `aiogram_nav.storage.redis.RedisNavigationRepository`, a stable prefix and Redis 7+ standalone with noeviction. See the sibling package’s `docs/redis.md` and `examples/redis_demo.py` for lease coordination, shared FSM storage, recovery and deployment limits. Kit adds no dependency extra until a usable distribution is published. No idle integration is required.

The follow-up Redis audit also guards cleanup after lease loss or reentrant navigation, preserves unproven/pending callback keyboards and validates sweep history. Custom presenters must honor the optional `CleanupRequest.ensure_owned` guard before each external cleanup operation. See the sibling package’s `docs/redis-audit.md`.

For combined use, install the compatible aiogram-idle[nav] or [nav,redis] extra and construct Navigation with integration.navigation_repository. Call only integration.install, not navigation.install first. See aiogram-idle/docs/navigation.md; the standalone navigation repository remains available without idle.
