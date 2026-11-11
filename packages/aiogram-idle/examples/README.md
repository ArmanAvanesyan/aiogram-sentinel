# Examples

Run from the repository root in the frozen development environment. Examples
read `BOT_TOKEN` only at startup. CLI help and automated tests do not need a token
and never send real Telegram messages; running a demo with a token does.

```sh
uv sync --frozen
uv run --no-sync python examples/demo.py --help
uv run --no-sync python examples/demo.py --controls reply
uv run --no-sync python examples/demo.py --controls inline
uv run --no-sync python examples/demo.py --controls commands
uv run --no-sync python examples/demo.py --controls hybrid --fsm
```

`demo.py` uses standalone memory storage and application-owned sample drafts.
`/draft` enters the activity, accepted text touches it, and `/status` displays safe
lifecycle metadata. Continue preserves the draft; Cancel and grace timeout invoke
application cleanup. `--after` and `--grace` select development timings.

For the optional navigation integration, install the adjacent compatible
`aiogram-nav` checkout through the frozen extra:

```sh
uv sync --frozen --extra nav --extra redis
uv run --no-sync python examples/navigation.py --style hybrid
```

`navigation.py` accepts the same four style names through `--style`. Use `/form`
and `/menu`; accepted form text resets inactivity. Without `NAV_REDIS_URL`, the
example is single-process and loses all records on restart. With that variable,
both the integrated idle backend and example FSM store use Redis. Its sample
business adapter is a contract demonstration, not a durable draft implementation.

Both entry points configure application logging only when run: global INFO and
package-scoped DEBUG. Credentials stay in environment variables. Do not add
message text, bot tokens or credential-bearing Redis URLs to diagnostics.

See [standalone usage](../docs/standalone.md), [Redis](../docs/redis.md) and
[optional navigation](../docs/navigation.md) for production boundaries.
