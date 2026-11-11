# aiogram-kit

**Community libraries for [aiogram](https://aiogram.dev) v3.** Each library is a
standalone package with its own docs, releases and issue tracker. Install only what
you need.

## Libraries

<div class="grid cards" markdown>

-   :material-shield-check: **aiogram-sentinel**

    ---

    Rate limiting, debouncing and error-handling middleware. Per-user and per-handler
    scopes, sliding-window throttling, memory or Redis storage for multi-worker bots.

    ```bash
    pip install aiogram-sentinel
    ```

    [:octicons-arrow-right-24: Documentation](https://armanavanesyan.github.io/aiogram-sentinel/)
    · [GitHub](https://github.com/ArmanAvanesyan/aiogram-sentinel)
    · [PyPI](https://pypi.org/project/aiogram-sentinel/)

-   :material-console-line: **aiogram-cmds**

    ---

    Bot command management. i18n-aware command menus, user profiles that decide which
    commands are visible, all Telegram command scopes, one-call auto setup.

    ```bash
    pip install aiogram-cmds
    ```

    [:octicons-arrow-right-24: Documentation](https://armanavanesyan.github.io/aiogram-cmds/)
    · [GitHub](https://github.com/ArmanAvanesyan/aiogram-cmds)
    · [PyPI](https://pypi.org/project/aiogram-cmds/)

</div>

## Using them together

The libraries do not depend on each other. A typical bot wires both at startup:

```python
from aiogram import Bot, Dispatcher
from aiogram_sentinel import Sentinel, SentinelConfig
from aiogram_cmds.auto_setup import setup_commands_auto

bot = Bot(token="...")
dp = Dispatcher()

async def on_startup() -> None:
    await Sentinel.setup(dp, SentinelConfig())
    await setup_commands_auto(bot)

dp.startup.register(on_startup)
```

!!! note "Meta package"
    The PyPI name [`aiogram-kit`](https://pypi.org/project/aiogram-kit/) is reserved
    for a future meta package that installs the whole kit with extras. Today it only
    carries a version marker.

## Contributing

Every library has its own contributing guide and issue tracker on GitHub.
aiogram-kit is a community project and is not affiliated with the aiogram maintainers.
