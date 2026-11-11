# Installation

Requires Python 3.10+ and `aiogram>=3.22,<4`.

```sh
python -m pip install aiogram-idle==0.3.0
# Optional standalone Redis backend:
python -m pip install 'aiogram-idle[redis]==0.3.0'
# Optional navigation integration:
python -m pip install 'aiogram-idle[nav]==0.3.0'
# Navigation and Redis together:
python -m pip install 'aiogram-idle[nav,redis]==0.3.0'
```

Base installations do not install Redis or aiogram-nav. The Redis-only extra does
not install navigation. The `nav` extra resolves a compatible aiogram-nav release
from PyPI; applications can also use either library independently.

## Source development

```sh
git clone https://github.com/ArmanAvanesyan/aiogram-idle.git
cd aiogram-idle
uv sync --frozen --python 3.12
uv run --no-sync python examples/demo.py --help
```

Both standalone and optional-extra development resolve published peers from the
index. No adjacent checkout is required. Use `uv sync --frozen --extra nav` for
navigation support. For joint development, explicitly install a local peer into
the environment with `uv pip install -e /absolute/path/to/aiogram-nav` and run
commands using `uv run --no-sync`; keep that override out of release artifacts and
the committed lock. See the [integration guide](navigation.md).

Redis storage requires a writable standalone Redis 7+ primary with `noeviction`.
It does not turn memory FSM or application draft storage into durable storage.
Read [Redis setup](redis.md) before enabling multiple workers.
