# Contributing to aiogram-sentinel

## Development setup

Use Python 3.10 or newer and uv. From a checkout:

```bash
uv sync --frozen --all-extras
```

This installs the locked development tools and optional Redis/Sentry integrations.
Application installs need only the extras they use; see [installation](docs/installation.md).

## Verification

```bash
uv run --no-sync ruff check .
uv run --no-sync black --check src tests
uv run --no-sync pyright
uv run --no-sync pytest tests/unit tests/integration --cov=aiogram_sentinel --cov-fail-under=80
uv run --no-sync mkdocs build --strict
uv build
uv run --no-sync python -m twine check dist/*
```

Ruff owns linting; Black owns formatting. Strict Pyright checks the library's
Python 3.10 public surface. Add meaningful regression tests for changed behavior;
the required test suite has an 80% coverage gate.

Redis integration tests need a disposable Redis server. Tests use unique prefixes
and delete only their own keys:

```bash
TEST_REDIS_URL=redis://localhost:6379/15 REQUIRE_REDIS=1 \
  uv run --no-sync pytest tests/unit tests/integration --cov=aiogram_sentinel --cov-fail-under=80
```

See [verification](docs/TESTING.md) for artifact isolation and dependency matrices.
Security scan commands and the generated-report policy are in
[reports/README.md](reports/README.md). Generated JSON belongs in CI artifacts,
not source control. Never include bot tokens, message content or Redis credentials
in examples, logs or bug reports.

## Repository convention

- `src/aiogram_sentinel/`: typed runtime package.
- `tests/`: unit, integration and optional performance diagnostics.
- `docs/` and `examples/`: user guidance and runnable examples.
- `CHANGES/`: Towncrier fragments; `CHANGELOG.md`: release history.
- `tools/`: repository automation; `reports/`: maintained verification evidence.
- `.github/`: workflows, issue forms and pull request guidance.

The internal layout follows Sentinel's middleware and storage responsibilities.
Do not introduce dependencies on aiogram-idle or aiogram-nav for shared tooling.

## Pull requests

Use a focused branch and describe the problem, resulting behavior and validation.
Keep public APIs typed and document observable changes. Add a fragment as described
in [CHANGES/README.md](CHANGES/README.md), using `feature`, `bugfix`, `doc`,
`removal` or `misc`. An unnumbered change can use
`CHANGES/+short-description.misc.rst`.

CI checks fragments against the pull request base. A `skip news` label exempts
changes that need no release note. Use conventional commit subjects such as
`fix(storage): preserve atomic expiry` or `docs: clarify installation`.

Report ordinary bugs through [GitHub issues](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues).
Report vulnerabilities privately using [SECURITY.md](SECURITY.md).
Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Releases and license

See [releasing](docs/releasing.md) for the maintainer procedure. Branch pushes and
pull requests do not publish packages; publishing requires an explicit release tag
and the configured GitHub publishing environment. Repository alignment does not
change the package version or create a release.

Contributions use the project's existing [MIT license](LICENSE).
