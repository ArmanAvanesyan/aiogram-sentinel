# Contributing to aiogram-nav

Use Python 3.10 or newer and uv. From a checkout:

```sh
uv sync --frozen --extra redis --python 3.12
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright src examples
uv run --no-sync pytest
uv run --no-sync mkdocs build --strict
uv run --no-sync python tools/check_version.py
uv build
uv run --no-sync twine check dist/*
```

The ordinary suite works without a Redis server and explicitly skips server-only
cases. For the required Redis suite, start a disposable Redis 7 server and run:

```sh
AIOGRAM_NAV_REDIS_URL=redis://localhost:6379/0 AIOGRAM_NAV_REQUIRE_REDIS=1 \
  uv run --no-sync pytest --cov=aiogram_nav --cov-report=term-missing
```

Tests use isolated prefixes; do not point development checks at production.
The required suite has an 80% combined line/branch coverage gate. Add regression
tests for changed behavior, including ownership and ambiguous-delivery cases.
The library does not configure logging; CLI examples enable safe debug output.
Never put bot tokens, Redis credentials or message content in reports or fixtures.

## Repository convention

- `src/aiogram_nav/`: typed runtime code, with `py.typed` shipped in artifacts.
- `tests/`: contracts, lifecycle, dispatcher, failure and backend tests.
- `examples/`: reply, inline, command-only, hybrid and Redis demonstrations.
- `docs/`: user guides, architecture, verification and release guidance.
- `CHANGES/`: Towncrier reStructuredText fragments; `CHANGELOG.md`: release history.
- `tools/`: repository automation; `reports/`: maintained verification evidence.
- `.github/`: CI, issue forms and pull request guidance.

Python 3.12 is the recommended development environment; Python 3.10 remains a
runtime and compatibility-test target. Run dependency security auditing on Python
3.11 or newer, as described in the report policy.

Generated coverage and security JSON belong in local ignored output or CI
artifacts. Follow [reports/README.md](reports/README.md) for security scans.

Add a fragment such as `CHANGES/+short-description.bugfix.rst` or an issue-numbered
fragment. Supported types are `feature`, `bugfix`, `doc`, `removal` and `misc`.
Preview with `uv run --no-sync towncrier build --draft`. Preserve standalone usage:
neither Redis nor aiogram-idle may become a mandatory dependency.

Describe the problem, resulting behavior and relevant validation in pull
requests. Use conventional commit subjects such as `fix(storage): preserve stale
receipt evidence`. Package publication is a separate maintainer action; see
[docs/releasing.md](docs/releasing.md).

Participation follows [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report
vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
