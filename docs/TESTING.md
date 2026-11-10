# Verification

Install the development environment with `uv sync --frozen --all-extras`.
The authoritative strict Pyright configuration is in `pyproject.toml` and checks
`src` against Python 3.10. The distribution includes `py.typed`.

```bash
uv run --no-sync ruff check .
uv run --no-sync black --check src tests
uv run --no-sync pyright
uv run --no-sync pytest tests/unit tests/integration --cov=aiogram_sentinel --cov-fail-under=80
```

Real Redis tests run only with `TEST_REDIS_URL` configured. Set `REQUIRE_REDIS=1`
to fail instead of skipping when the URL is missing. Use a disposable Redis
server. Tests create unique prefixes and remove only their own keys; they never
flush the database. An unreachable configured server fails the tests.

```bash
TEST_REDIS_URL=redis://localhost:6379/15 REQUIRE_REDIS=1 \
  uv run --no-sync pytest tests/integration
```

The real dispatcher regression test feeds updates through `Dispatcher.feed_update`
and verifies that application guards survive installation and hook changes.
Real Redis tests cover atomic fixed-window counting, expiry, namespacing and
concurrent debounce. Sentinel does not provide durable workflows, lease ownership
or recovery receipts.

CI runs these required checks on pull requests and main: Ruff, Black, strict
Pyright, wheel/sdist builds, dependency-isolated artifact imports, Python
3.10–3.13 with the latest resolvable aiogram 3.x, and aiogram 3.0.0 on Python 3.10.
The aggregate Required Checks job fails for failed, cancelled or skipped
required jobs, except the changelog check when no PR check is applicable or
`skip news` is selected. Security scans and artifact checks are required. Benchmarks under `tests/perf` are manual diagnostics and are not a
release or correctness gate. Local verification covers only the interpreters
actually listed in the review report; a configured matrix is not evidence that
remote CI has run.

```bash
uv build
uvx twine check dist/*
uv venv /tmp/sentinel-base
uv pip install --python /tmp/sentinel-base/bin/python dist/*.whl
/tmp/sentinel-base/bin/python tools/check_install.py
```

Repeat in a fresh environment using the sdist to check both artifacts. The
installation probe asserts version consistency, typing marker, memory startup,
and a useful missing-extra error without Redis or Sentry installed.

## Framework compatibility environments

CI solves each endpoint's complete dependency graph in a fresh `.test-venv`
rather than replacing aiogram inside the locked development environment. The
minimum aiogram 3.0 endpoint requires `typing-extensions<4.8`; its test profile
therefore uses `pytest-asyncio<1`, since newer releases import `TypeIs`.

```bash
uv venv --python 3.10 .test-venv
uv pip install --python .test-venv/bin/python '.[dev,redis,sentry]' 'aiogram==3.0.0' 'pytest-asyncio<1'
TEST_REDIS_URL=redis://localhost:6379/15 REQUIRE_REDIS=1 \
  .test-venv/bin/python -m pytest tests/unit tests/integration --cov=aiogram_sentinel --cov-fail-under=80
```

These endpoint environments verify compatibility; the frozen default environment
is audited separately. Linux-only locked dependencies are included by running
the security job on Linux.

Dependency auditing runs on Python 3.11+ because the audit tool's patched
transitive dependencies require it. Runtime and test support still includes
Python 3.10.
