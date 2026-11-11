# Contributing

Use Python 3.12 and uv for development; Python 3.10–3.14 are compatibility targets.

```sh
uv sync --frozen --extra redis --python 3.12
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync pytest
uv run --no-sync mkdocs build --strict
uv build
uv run --no-sync twine check dist/*
```

To require real Redis tests, set `AIOGRAM_COORDINATION_REDIS_URL` to a disposable
server and `AIOGRAM_COORDINATION_REQUIRE_REDIS=1`. Tests isolate lock prefixes and
never flush a database. Never use a production URL. Required real-server coverage
is at least 80%; ownership and failure assertions may not be skipped to reach it.

Runtime lives in src/, tests in tests/, runnable examples in examples/, user and
release docs in docs/, repository automation in tools/, maintained evidence in
reports/ and changelog fragments in CHANGES/. Use feature/bugfix/doc/removal/misc
rst fragments. Generated security/coverage JSON belongs in ignored output or CI
artifacts. Do not commit credentials, environments or generated distributions.

Preserve optional Redis and the absence of Idle/Nav/Kit imports. Describe changes,
validation and compatibility impact in PRs. Follow CODE_OF_CONDUCT.md and report
security concerns through SECURITY.md. Publication is a separate authorized action.
