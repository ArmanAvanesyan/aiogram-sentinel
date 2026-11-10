# Runnable examples

Run from a checkout with Python 3.10+:

```sh
uv sync --all-extras --all-groups --frozen
export BOT_TOKEN="<token from BotFather>"
uv run python examples/basic_bot.py
```

| Example | Purpose |
| --- | --- |
| `basic_bot.py` | Default command registration through `setup_commands_auto` |
| `profile_based_bot.py` | Application-selected guest/member profiles through `update_profile` |
| `dynamic_bot.py` | Change private-chat menus when a demo session starts or finishes |
| `i18n_bot.py` | Translated menus and messages using aiogram's gettext adapter |

Menus describe available commands; handlers must still enforce authorization.
The profile example uses a process-local demo membership set, which is lost on
restart and performs no real registration. These examples do not provide Redis
storage, authentication, persistent sessions or background scheduling.

The examples create bots and configure logging only from their entry points.
Set `LOG_LEVEL=DEBUG` for verbose development logs. Never commit tokens or log
message bodies or credentials. Failures propagate and bot sessions are closed.

## Gettext example

Install aiogram's optional i18n requirements and compile the included catalogs:

```sh
uv pip install 'aiogram[i18n]>=3,<4'
uv run pybabel compile -d examples/locales -D messages
uv run python examples/i18n_bot.py
```

The locale follows Telegram's user language, with English fallback. Catalog paths
are resolved relative to the script. Generated `.mo` files are local build output.
See [i18n integration](../docs/tutorials/i18n-integration.md) for application usage.

## Application-owned profiles and confirmation hashes

`python examples/application_profiles.py --dry-run` sends no Telegram requests.
Without that flag, set `BOT_TOKEN`; the example configures one default-language
profile and skips the second identical request using a caller-owned confirmation.
See the [0.2 migration guide](../docs/migration-0.2.md) for limitations.
