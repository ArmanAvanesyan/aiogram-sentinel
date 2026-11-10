# Testing

Install the locked environment with Python 3.10 or newer:

```bash
uv sync --all-extras --all-groups --frozen
```

## Required checks

```bash
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright
uv run --frozen pytest tests/unit tests/integration --cov=src/aiogram_cmds --cov-report=term-missing --cov-fail-under=80
uv run --frozen mkdocs build --strict
uv build
uv run --frozen twine check dist/*
```

Unit tests cover command configuration, policies, translation, scope validation
and manager failure behavior. Integration tests exercise configuration through
fake Telegram sessions. Tests require neither a real bot token nor network calls
to Telegram. The 80% coverage gate applies to the combined unit/integration suite.
Actual measured counts and compatibility results are recorded in
[Local verification](verification.md), rather than treated as permanent targets.

Run performance tests separately:

```bash
uv run --frozen pytest tests/perf
```

CI checks advertised CPython 3.10–3.13 versions and minimum/latest aiogram
boundaries. Additional platform, PyPy and performance jobs run on the configured
scheduled/manual paths. Minimum-version compatibility is separate from auditing
the current locked environment; old dependencies are not recommended for production.
Wheel/sdist checks install artifacts into isolated environments and verify version
metadata, typed markers and the absence of optional Redis in base installations.

## Security checks

```bash
uv run --frozen bandit -c pyproject.toml -r src
uv run --frozen pip-audit
```

CI uploads generated JSON reports as artifacts and fails on findings. Local outputs
are ignored. See the [repository security policy](https://github.com/ArmanAvanesyan/aiogram-cmds/blob/main/SECURITY.md)
for private reporting guidance. Library tests do not validate application-owned
Redis persistence, distributed coordination or authorization.
