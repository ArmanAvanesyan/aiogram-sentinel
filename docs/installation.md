# Installation

Requires Python 3.10+ and `aiogram>=3.22,<4`.

```sh
python -m pip install aiogram-idle==0.2.0
# Optional standalone Redis backend:
python -m pip install 'aiogram-idle[redis]==0.2.0'
# Optional navigation integration:
python -m pip install 'aiogram-idle[nav]==0.2.0'
# Navigation and Redis together:
python -m pip install 'aiogram-idle[nav,redis]==0.2.0'
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

Standalone frozen sync works without the peer repository. Regenerating the lock
or selecting the `nav` extra in this development checkout uses the adjacent
`../aiogram-nav` source declared in `pyproject.toml`. Clone a compatible navigation
checkout there before selecting that extra. This source override does not change
the wheel's dependency metadata or affect pip installation from PyPI. See the
[integration guide](navigation.md) for the optional combined example.

Redis storage requires a writable standalone Redis 7+ primary with `noeviction`.
It does not turn memory FSM or application draft storage into durable storage.
Read [Redis setup](redis.md) before enabling multiple workers.
