# Quickstart

The runnable demo supplies an application adapter, presenter and explicit activity
acceptance. It keeps sample drafts in memory; it is not a production draft store.

```sh
uv sync --frozen --python 3.12
uv run --no-sync python examples/demo.py --help
```

Provide `BOT_TOKEN` through your environment, then select the prompt controls:

```sh
uv run --no-sync python examples/demo.py --controls reply
uv run --no-sync python examples/demo.py --controls inline
uv run --no-sync python examples/demo.py --controls commands
uv run --no-sync python examples/demo.py --controls hybrid
uv run --no-sync python examples/demo.py --controls inline --fsm
```

These commands send real messages when run with a token. Send `/draft`, enter some
text and wait for the prompt. Continue preserves the draft; Cancel or grace expiry
runs the application's cleanup and restores its UI. `/status` shows lifecycle
metadata. `--after` and `--grace` select demonstration intervals.

For your application:

1. Register named exempt, prompt or quiet-restore policies.
2. Supply authorization/resumability inspection and idempotent business adapters.
3. Construct `IdleRuntime` with a backend and presenter, and explicitly enable
   creation through configuration.
4. Install the runtime before business routers and before polling.
5. Open a session and call `enter` or guarded `touch` only after accepted input.

Read the [standalone guide](standalone.md) before connecting durable business
effects. See [optional navigation](navigation.md) for its separate four-style demo.
