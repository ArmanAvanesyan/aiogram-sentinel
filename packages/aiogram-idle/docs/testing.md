# Testing and compatibility

Runtime support is Python 3.10+ and aiogram 3.22 through the latest compatible
3.x release. CI covers Python 3.10–3.14 with current aiogram and the minimum 3.22.0
endpoint on Python 3.10–3.13. The old dependency pins do not support Python 3.14,
so that minimum combination is excluded. Redis jobs cover servers 7/8 and
minimum/current supported redis-py clients (`>=5.0.8,<8`).

From the checkout:

```sh
uv sync --frozen --extra redis --python 3.12
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync pytest
uv run --no-sync mkdocs build --strict
```

Without a Redis URL, real-server tests skip explicitly. Storage, concurrency and
recovery changes require a disposable real server:

```sh
AIOGRAM_IDLE_REDIS_URL=redis://127.0.0.1:6379/0 \
AIOGRAM_IDLE_REQUIRE_REDIS=1 \
  uv run --no-sync pytest --cov=aiogram_idle --cov-report=term-missing
```

Tests use unique prefixes and never flush application databases, but script-cache
tests use `SCRIPT FLUSH`. Dedicate the entire test server to this run. CI requires
the server configuration and an 80% coverage gate. Tests use fake Telegram sessions;
they do not send bot messages.

Standalone jobs do not install navigation. A separate automatic integration job
checks out compatible `aiogram-nav` source, checks the optional strict type profile
and runs integration/component tests. The manual peer-revision workflow exercises
the broader optional Python/Redis matrix. For local combined verification:

```sh
uv sync --frozen --extra redis --extra nav
uv run --no-sync pyright --project pyright-nav.json
AIOGRAM_IDLE_REDIS_URL=redis://127.0.0.1:6379/0 \
AIOGRAM_IDLE_REQUIRE_REDIS=1 \
  uv run --no-sync pytest --cov=aiogram_idle --cov-config=coverage-nav.toml
```

## Security and artifacts

Run dependency auditing on Python 3.11 or newer; CI uses 3.12. This development-tool
requirement avoids vulnerable transitive tooling on older Python and does not
change runtime support. Source scans include narrowly documented internal-invariant
assert suppressions, not a global exclusion of input or authorization checks.

```sh
uv run --no-sync bandit -r src -f json -o bandit-report.json
uv run --no-sync pip-audit --skip-editable --format json --output pip-audit-report.json
uv build
uv run --no-sync twine check dist/*
uv run --no-sync python tools/check_artifacts.py dist/*.whl dist/*.tar.gz
```

Generated reports are ignored locally and retained as CI artifacts. Artifact smoke
checks install wheel/sdist independently with neither Redis nor navigation present.
See [dated verification results](verification.md); configured matrix jobs are not
evidence that every endpoint has run locally.
