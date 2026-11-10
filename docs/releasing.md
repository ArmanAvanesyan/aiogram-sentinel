# Releasing

Package releases are deliberate maintainer actions. A branch push runs verification
and does not publish to PyPI. The existing release workflow runs only for version
tags matching `v*.*.*`; it requires the configured `pypi` environment and trusted
publishing permissions. Do not create a release tag merely to update repository
conventions.

## Prepare a release

1. Review user-facing change fragments in `CHANGES/`. Use Towncrier types
   `feature`, `bugfix`, `doc`, `removal` and `misc`.
2. Choose a version, update `pyproject.toml` and
   `src/aiogram_cmds/version.py` together, and render/review the changelog:

   ```bash
   uvx towncrier build --draft --version X.Y.Z
   uvx towncrier build --version X.Y.Z
   ```

3. Install the locked development environment and run the contribution checks:

   ```bash
   uv sync --all-extras --all-groups --frozen
   uv run --frozen ruff check .
   uv run --frozen ruff format --check .
   uv run --frozen pyright
   uv run --frozen pytest tests/unit tests/integration --cov=src/aiogram_cmds --cov-fail-under=80
   uv run --frozen mkdocs build --strict
   uv run --frozen bandit -c pyproject.toml -r src
   uv run --frozen pip-audit
   uv run --frozen python tools/check_version_tag.py
   uv build
   uv run --frozen twine check dist/*
   ```

4. Verify the wheel and sdist in clean environments, including metadata/runtime
   version equality, `py.typed`, base installation without Redis, and supported
   aiogram dependency boundaries. Review the CI results and commit the release
   preparation through the usual review process.

## Publish

After approving the release commit, a maintainer creates the matching `vX.Y.Z`
tag and pushes that tag. The release workflow checks version consistency, builds
and checks distributions, publishes to PyPI and creates a GitHub release. Review
that workflow and environment configuration before use. Existing tags must not be
deleted or rewritten; correct a faulty release with a new version.

`tools/deploy.sh` and `tools/deploy.ps1` are legacy maintainer conveniences that
create and push tags. They are publication actions, not application-deployment
scripts, and are not part of ordinary development. Prefer the explicit reviewed
release steps above.

## Documentation

Documentation builds strictly on branch pushes and pull requests. Publishing to
GitHub Pages requires a manual Documentation workflow dispatch with deployment
enabled on `main`. Package release and documentation publication are separate
operations. Consuming applications own their deployment processes.
