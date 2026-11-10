# Examples

`minimal_bot.py` demonstrates process-local memory storage, duplicate suppression,
rate-limit notifications and friendly application errors. Handlers are registered
on the router returned by `Sentinel.setup`, so its middleware actually protects
them. The example uses explicit per-setup error configuration and no deprecated
decorators.

From the repository root:

```bash
uv sync --frozen --all-extras
export BOT_TOKEN='your-token'
uv run --no-sync python examples/minimal_bot.py
```

Send `/start` for instructions. Send `/spam one` then `/spam two` immediately:
the first is accepted and the second receives a rate-limit response. Identical
messages within two seconds are silently suppressed before rate limiting. After
the rate window passes, `/error` demonstrates a friendly validation response.
`/help` displays command guidance. Debouncing suppresses duplicates; it does not
delay execution of the first message.

Debug logging is enabled for the example and Sentinel inside `main`; HTTP logging
stays at the application's INFO level. Importing the example does not configure
logging, access credentials or start polling. Polling failures propagate and
sessions/storage close on exit. Do not enable verbose HTTP logs with real tokens.

Memory state is single-process and disappears on restart. For the Redis backend,
install the `redis` extra and follow [Redis storage](../docs/tutorials/redis-storage.md).
Redis uses fixed-window counting; memory uses sliding-window counting.
