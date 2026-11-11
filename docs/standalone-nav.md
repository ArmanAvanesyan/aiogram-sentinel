# Standalone aiogram-nav

Install navigation independently from PyPI:

```sh
uv pip install 'aiogram-nav==0.3.1'
# For persistent navigation across processes:
uv pip install 'aiogram-nav[redis]==0.3.1'
```

Python 3.10+ and aiogram 3.22+ within 3.x are required. Neither installation
requires aiogram-idle. Navigation does not start an idle worker. The `aiogram-kit`
distribution remains a lightweight marker; install libraries directly.

The registry and explicit input bindings support reply, inline, command and hybrid
navigation. Navigation prepares rendering before external effects and commits the
location after completion. It preserves partial or unknown rendering evidence
rather than automatically resending it. Back preserves business drafts; Cancel
invokes an explicit application hook instead of clearing arbitrary FSM fields.

For application-owned rendering, use the documented tracking mode. A single owner
should perform message cleanup. See the [public guide](libraries/aiogram-nav/README.md)
for rendering, router placement, intentional root handlers and custom coordinators.

## Runnable examples and development

```sh
git clone https://github.com/ArmanAvanesyan/aiogram-kit.git
cd aiogram-kit
uv sync --frozen --all-packages --all-groups --all-extras
# Export BOT_TOKEN in your environment first.
uv run --no-sync python packages/aiogram-nav/examples/demo.py --style reply
uv run --no-sync python packages/aiogram-nav/examples/demo.py --style inline
uv run --no-sync python packages/aiogram-nav/examples/demo.py --style commands
uv run --no-sync python packages/aiogram-nav/examples/demo.py --style hybrid --fsm
```

Memory state is single-process, bounded and lost on restart. For Redis, use
`aiogram_nav.storage.redis.RedisNavigationRepository`, a stable namespace and Redis
7+ standalone with `noeviction`. Keep the application FSM storage and normalized
isolation consistent across handlers and workers. See the
[Redis guide](libraries/aiogram-nav/docs/redis.md) and
[Redis example](https://github.com/ArmanAvanesyan/aiogram-kit/blob/main/packages/aiogram-nav/examples/redis_demo.py).

Callback tokens bind to the actor and conversation; stale or foreign callbacks do
not authorize a transition. Reply labels and bare commands lack prompt-specific
provenance. Custom presenters must honor `CleanupRequest.ensure_owned` before each
external cleanup operation. The [recovery audit](libraries/aiogram-nav/docs/redis-audit.md)
describes lease loss, cleanup ownership and retained recovery evidence.

## Optional Idle integration

Install `aiogram-idle[nav]` or `aiogram-idle[nav,redis]` only when needed.
Construct Navigation with `integration.navigation_repository` and call only
`integration.install`. See the [combined guide](libraries/aiogram-idle/docs/navigation.md).
Navigation/activity/deadline updates are atomic; Telegram, business stores and FSM
writes are external effects. Both libraries remain fully usable independently.
