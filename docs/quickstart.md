# Standalone navigation quickstart

This checkout contains standalone memory and optional Redis implementations. It is a
development distribution not yet on PyPI. From a checkout, install in a bot environment:

```sh
uv venv --python 3.12
uv pip install -e .
```

The package requires Python 3.10+ and aiogram 3.22 or newer in the 3.x series. It
requires neither aiogram-idle nor Redis. An [optional idle integration](idle-integration.md)
is available separately. Optional [Redis navigation storage](redis.md)
is available through the `redis` extra.

## Run the neutral demo

From the checkout:

```sh
uv sync --python 3.12
uv run python examples/demo.py --help
```

Set `BOT_TOKEN` in the environment before running a bot, then choose a style:

```sh
uv run python -m examples.reply_only.main
uv run python -m examples.inline_only.main
uv run python -m examples.commands_only.main
uv run python -m examples.hybrid.main --fsm
```

The same application also accepts `--style reply`, `--style inline`,
`--style commands` or `--style hybrid` through `examples/demo.py`. `--fsm` puts the
sample draft in application-owned FSM storage instead of its plain dictionary.
Both stores are memory-only and disappear when the process restarts.

Send `/start` to install the initial screen. Open a panel, go Back, open the draft
editor and enter sample text. Back preserves the draft; Cancel calls the explicit
application hook that discards it. `/status` reports node/revision metadata and the
saved character count, without logging draft content. The command-only variant
uses `/panel`, `/edit`, `/back`, `/home`, `/cancel` and `/refresh`. `/start` is the
bootstrap command for every variant.

Examples enable safe development logging only in their CLI entry point. Constructing
`build_demo(bot, args)` does not poll Telegram or make network calls. The library
does not configure logging globally and never reads `BOT_TOKEN` itself.

## Connect an application

1. Register roots and immutable nodes with stable IDs and renderer keys.
2. Construct a `MemoryNavigationRepository`, a presenter and `Navigation`.
3. Bind only the commands, reply labels and inline actions your application wants.
4. Install navigation before including business routers.
5. In handlers, use the injected `nav_context`; record accepted draft input with
   `touch()`, rather than treating every received update as activity.

See [concepts](concepts.md), [the public API](public-api.md), and
[migration](migration.md) for the responsibilities at each boundary.
