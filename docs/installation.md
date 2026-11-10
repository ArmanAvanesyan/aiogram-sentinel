# Installation

Requires Python 3.10+ and `aiogram>=3.22,<4`. This development distribution has not
been published to PyPI. Clone and install the checkout:

```sh
git clone https://github.com/ArmanAvanesyan/aiogram-idle.git
cd aiogram-idle
uv pip install -e .
# Optional standalone Redis backend:
uv pip install -e '.[redis]'
```

Use an existing environment, or create one with `uv venv` first. Base installations
do not install Redis or aiogram-nav. To develop with the frozen tool environment:

```sh
uv sync --frozen --python 3.12
uv run --no-sync python examples/demo.py --help
```

Standalone frozen sync works without the peer repository. Regenerating the lock
or selecting the `nav` extra uses the adjacent `../aiogram-nav` source declared
in `pyproject.toml`. Clone a compatible navigation checkout there before selecting
that extra. See the [integration guide](navigation.md) for installation in another
bot environment and the optional combined example.

Redis storage requires a writable standalone Redis 7+ primary with `noeviction`.
It does not turn memory FSM or application draft storage into durable storage.
Read [Redis setup](redis.md) before enabling multiple workers.
