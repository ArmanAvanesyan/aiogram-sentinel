# Contributing to aiogram-cmds

Use Python 3.10 or newer and [uv](https://docs.astral.sh/uv/). Fork the repository,
create a branch from `main`, and install the locked development environment:

```bash
git clone https://github.com/ArmanAvanesyan/aiogram-cmds.git
cd aiogram-cmds
uv sync --all-extras --all-groups --frozen
```

## Checks

```bash
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright
uv run --frozen pytest tests/unit tests/integration --cov=src/aiogram_cmds --cov-fail-under=80
uv run --frozen pytest tests/perf
uv run --frozen mkdocs build --strict
uv build
uv run --frozen twine check dist/*
uv run --frozen bandit -c pyproject.toml -r src
uv run --frozen pip-audit
```

Ruff owns formatting and linting; Pyright checks the public package in strict
mode. Add meaningful tests for changed behavior. The required unit/integration
coverage gate is 80%; current measured results are in [verification](docs/verification.md).
Tests use controlled Telegram sessions and must not require a real bot token.
There is no configured pre-commit hook; run the checks explicitly.

## Repository convention

The related aiogram libraries share these responsibilities without sharing their
internal modules or test layouts:

| Path | Responsibility |
| --- | --- |
| `.github/` | CI, issue templates and pull-request guidance |
| `CHANGES/` | Towncrier reStructuredText change fragments |
| `docs/` | Usage, API, architecture, testing and release documentation |
| `examples/` | Runnable application examples |
| `src/aiogram_cmds/` | Typed public package and `py.typed` marker |
| `tests/` | Unit, integration and performance verification |
| `tools/` | Repository automation; no separate `scripts/` directory |
| `reports/` | Optional maintained review evidence, not generated scan output |

`pyproject.toml` declares packaging and quality settings; `uv.lock` records the
development resolution. Runtime versions are exported from `version.py` and
checked against distribution metadata. Generated coverage and audit files are
ignored and uploaded by CI as artifacts.

## Changes and pull requests

Use type hints, Google-style docstrings and Ruff formatting. Keep changes focused,
preserve compatibility where possible, and update the relevant examples and docs.
Add a fragment following [CHANGES/README.md](CHANGES/README.md), using `feature`,
`bugfix`, `doc`, `removal` or `misc`. A change without an issue number can use a
name such as `CHANGES/+repository-conventions.misc.rst`.

Before opening a pull request, run the relevant checks and describe the resulting
behavior and validation. Use a clear conventional commit subject such as
`fix: propagate command update failures`. Report bugs with reproduction steps;
use [SECURITY.md](SECURITY.md) for vulnerabilities rather than public issues.

Releases are maintainer actions described in [docs/releasing.md](docs/releasing.md).
A normal branch push does not publish a package. Follow the
[Code of Conduct](CODE_OF_CONDUCT.md). Contributions use the existing
[MIT license](LICENSE).
