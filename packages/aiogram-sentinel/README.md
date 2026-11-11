# aiogram-sentinel

Rate limiting and debouncing for aiogram 3. Sentinel protects handlers on its
router and descendant routers while retaining application authorization middleware.

## Install

```sh
pip install aiogram-sentinel
# Optional shared Redis storage:
pip install 'aiogram-sentinel[redis]'
```

## Protect an application router

```python
from aiogram import Dispatcher, Router
from aiogram_sentinel import ActionPolicy, Sentinel, SentinelConfig, ThrottleCfg

app = Router()
features = Router()
app.include_router(features)
# Register application handlers on features or app, then during async startup:
dp = Dispatcher()
router, infra = await Sentinel.setup(
    dp,
    SentinelConfig(
        bucket_mode="action_kind",
        action_policies={
            "message": ActionPolicy(throttle=ThrottleCfg(rate=5, per=10)),
            "command": ActionPolicy(throttle=ThrottleCfg(rate=3, per=10)),
            "callback_query": ActionPolicy(throttle=ThrottleCfg(rate=20, per=10)),
        },
    ),
    router=app,
)
```

These rates are examples, not new defaults. `bucket_mode="shared"` remains the
default, with the existing limit of 5 events per 10 seconds and 2-second debounce.
A command is a message with an initial Telegram `bot_command` entity. Command,
message and callback namespaces are distinct only when explicitly requested.

**Attachment matters:** middleware on a sibling router does not wrap another
router's handlers. Pass the application's ancestor router to `setup`, or register
handlers on the returned router. Startup warns once when its protected subtree
has no message/callback handlers. Do not attach the router to the Dispatcher
before calling `setup`.

Named handler policies and legacy decorators now resolve the registered aiogram
callback, including on aiogram 3.31. See [configuration](docs/configuration.md) for
precedence and explicit `/start` or callback-prefix exemptions. Exemptions bypass
only Sentinel spam protections, never application guards.

## Infrastructure failures

`ErrorConfig(reraise_exceptions=(TimeoutError,))` propagates matching exceptions
unchanged instead of sending friendly feedback. Add `redis.exceptions.RedisError`
when using Redis, and `aiogram_sentinel.exceptions.BackendOperationError` for
failures wrapped by Sentinel storage. This alone does not select an HTTP status: Dispatcher error
handlers must re-raise, and a foreground webhook adapter must map the failure to
503. Background acknowledgement cannot be changed retroactively.

See the [application integration guide](docs/application-integration.md) for
existing-client ownership, middleware/error ordering and the webhook recipe.

## Compatibility and verification

| Component | Supported/tested contract |
| --- | --- |
| Python | 3.10–3.13 in required CI |
| aiogram | >=3.0,<4; minimum 3.0 and current 3.x tested |
| redis-py | Optional >=5.0.8,<8; minimum/current endpoints tested |
| Redis server | 7 and 8 tested; older servers are not qualified |
| Memory storage | Single process/event loop; sliding-window rate limiter |
| Redis storage | Shared clients; fixed-window counter with atomic expiry |

Redis rate limiting requires `EVAL`, `INCR`, `TTL`, `EXPIRE`, `GET`; debounce
requires `SET` with `NX`/`EX`. The middleware's retry-after lookup also uses `TTL`.
No `INFO`, `ROLE` or `CONFIG` privileges are required by Sentinel. Availability,
eviction and persistence remain deployment responsibilities; Sentinel does not
provide Idle/Nav scheduling or durable business-effect recovery.

- [Migration to 1.2](docs/migration-1.2.md)
- [Configuration](docs/configuration.md), [API](docs/api/core.md), [examples](examples/README.md)
- [Testing](docs/TESTING.md), [release procedure](docs/releasing.md)
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), [MIT license](LICENSE)

The library never configures logging globally. Examples enable scoped debug output
and use recording Telegram sessions in tests; no real messages are sent by tests.

### Native companion: publication withheld

The source includes optional `engine="rust"` memory infrastructure, but the
native companion will not be published for 1.3.1: serial qualification measured
11.65% and 7.63% CPU reductions in the selected workloads, below the required
20%. Latency measurements were unstable, so no tail-latency gain is claimed.
Python remains the default and the optimized base package can ship independently.
There is no native release or `[native]` extra; the core remains available from
source. See the [host-specific benchmark decision](native/BENCHMARKS.md) and
[engine selection and semantics](docs/native-engine.md).
