# Application-owned integration

## Attach to an ancestor

`Sentinel.setup(dp, cfg, router=app_root)` installs middleware on `app_root`
and includes it in the Dispatcher. Put feature routers beneath that root. A
returned/default Sentinel router is valid when handlers are registered on it;
it does not retroactively protect sibling routers or Dispatcher-root handlers.
Register handlers before emitting startup so the attachment warning is useful.
Hooks update only Sentinel's owned proxy and preserve application middleware.

## Policies and action kinds

```python
from aiogram_sentinel import (
    ActionPolicy, DebounceCfg, SentinelConfig, SentinelExemptions, ThrottleCfg,
)

cfg = SentinelConfig(
    bucket_mode="action_kind",
    action_policies={
        "message": ActionPolicy(throttle=ThrottleCfg(5, 10)),
        "command": ActionPolicy(throttle=ThrottleCfg(3, 10)),
        "callback_query": ActionPolicy(throttle=ThrottleCfg(20, 10), debounce=DebounceCfg(1)),
    },
    exemptions=SentinelExemptions(commands=("start",), callback_prefixes=("readonly:",)),
)
```

Choose these rates for your application. No commands or prefixes are exempt by
default. Command names omit `/` and optional bot suffixes; `/start@ExampleBot`
with an initial command entity matches `start`. Slash text without that entity
is an ordinary message. Prefix matching is literal and configured by the app;
it does not prove callback ownership or grant authorization.

Exemptions bypass throttle and debounce only. Otherwise precedence is:

1. Per-update `sentinel_throttle_cfg` / `sentinel_debounce_cfg` injected by filters
   or earlier middleware (legacy `sentinel_rate_limit` / `sentinel_debounce` values
   also work, below their typed equivalents).
2. Named policies on the registered handler; later names override earlier names
   of the same protection kind.
3. Legacy handler decorators, retained for compatibility.
4. Matching `ActionPolicy` protection; `None` inherits the global default.
5. Existing global defaults.

`Sentinel.setup` installs `PolicyResolverMiddleware` before debounce and throttle.
If assembling middleware manually, install the public
`aiogram_sentinel.middlewares.policy_resolver.PolicyResolverMiddleware(registry, cfg)`
first; per-handler and action defaults are resolved by that stage, not by the
standalone throttle/debounce classes. Do not install a second resolver on a chain
already created by `setup`.

`sentinel_action_kind` reaches handlers as `message`, `command` or
`callback_query`. Named policies keep their explicit scopes/buckets/methods.
`action_kind` adds a bounded kind namespace while preserving those bucket choices;
`shared` preserves existing key behavior. Key changes are opt-in: an existing
shared-window count is not transferred into newly split kind windows.

## Reuse a Redis client

```python
from aiogram_sentinel import InfraBundle, Sentinel, SentinelConfig
from aiogram_sentinel.storage import RedisDebounce, RedisRateLimiter

# redis_client is created, authenticated and closed by the application.
cfg = SentinelConfig(backend="redis", redis_prefix="mybot")
infra = InfraBundle(
    rate_limiter=RedisRateLimiter(redis_client, prefix="mybot"),
    debounce=RedisDebounce(redis_client, prefix="mybot"),
)
router, infra = await Sentinel.setup(dp, cfg, router=app_root, infra=infra)
```

Sentinel does not close a supplied client. Stop admitting updates, drain handlers,
then close application FSM resources and the shared client in the application's
shutdown sequence. Use a distinct prefix per bot/environment; the key builder
prefix cannot contain its `:` separator. Reusing a client does not mean reusing
another library's keys or taking ownership of its connection.

Qualified servers are Redis 7 and 8. The rate limiter uses one `EVAL` for
`INCR` plus `TTL`/`EXPIRE`, including repair of old counters with no TTL.
`GET` reads remaining counts; `TTL` estimates retry delay. Debounce uses
`SET key value NX EX seconds`. Configure ACL permissions for the commands
inside Lua as well as `EVAL`, and key-pattern access to the selected prefix.
Sentinel does not issue `INFO`, `ROLE` or `CONFIG GET` and does not require a
particular persistence policy. Eviction/restart can reset counters; use suitable
Redis deployment controls if that is unacceptable. Sentinel's fixed Redis window
and sliding memory window intentionally have different boundary behavior.

## Error middleware and webhook retries

`ErrorHandlingMiddleware` normally catches `Exception`, sends configured friendly
feedback and returns `None`. Such handled exceptions do not reach `dp.errors`.
Configure passthrough for infrastructure failures before installing Sentinel:

```python
from redis.exceptions import RedisError
from aiogram_sentinel import ErrorConfig
from aiogram_sentinel.exceptions import BackendOperationError

errors = ErrorConfig(
    reraise_exceptions=(RedisError, TimeoutError, BackendOperationError),
)
router, infra = await Sentinel.setup(dp, cfg, router=app_root, error_config=errors)
```

Sentinel storage wraps driver failures in `BackendOperationError`; include that
public exception for storage-layer passthrough, not just raw driver errors.
Matching exceptions are re-raised unchanged before friendly messages or observer
hooks; subclasses also match. `asyncio.CancelledError` is never swallowed.
Dispatcher error handlers that recognize infrastructure failures must re-raise
rather than return a handled result. Other error handlers can intentionally
consume failures, so Sentinel alone cannot guarantee webhook retry behavior.

For aiohttp's `SimpleRequestHandler`, use `handle_in_background=False` and an
application middleware mapping propagated failures to 503:

```python
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

@web.middleware
async def retry_infrastructure(request, handler):
    try:
        return await handler(request)
    except (RedisError, TimeoutError, BackendOperationError):
        return web.Response(status=503)

web_app = web.Application(middlewares=[retry_infrastructure])
SimpleRequestHandler(dp, bot, handle_in_background=False).register(web_app, path="/webhook")
```

A webhook already acknowledged in background mode cannot later return 503.
Retries can repeat application side effects; keep business idempotency in the
application. The test suite verifies the complete foreground HTTP/Dispatcher
path using a real local server and a recording/no-network bot.
