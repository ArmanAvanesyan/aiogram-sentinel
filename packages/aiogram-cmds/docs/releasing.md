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

Publication is a manual dispatch from a matching version tag. A branch push,
tag push or GitHub release alone does not publish to PyPI. The existing PyPI
Trusted Publisher remains bound to `release.yml` and the `pypi` environment.

After the reviewed commit and successful CI, create its `vX.Y.Z` tag. Build and
verify the wheel and sdist from that exact source, create `SHA256SUMS` containing
exactly those two filenames, and upload those files to the matching GitHub
release. Keep the independently verified digest of the manifest.

```sh
gh workflow run release.yml --ref vX.Y.Z -f manifest_sha256=<reviewed-manifest-digest>
```

The workflow checks tag/version equality, filenames, metadata and all artifact
hashes before uploading those exact bytes through Trusted Publishing. It does
not rebuild or substitute distributions. Confirm workflow success, compare PyPI
hashes, and verify fresh standalone installation from PyPI afterward.

Never move release tags or replace published files. Correct a faulty release
with a new version. `tools/deploy.sh` and `tools/deploy.ps1` are legacy tag
preparation helpers; they do not replace the explicit reviewed upload procedure.

## Documentation

Documentation builds strictly on branch pushes and pull requests. Publishing to
GitHub Pages requires a manual Documentation workflow dispatch with deployment
enabled on `main`. Package release and documentation publication are separate
operations. Consuming applications own their deployment processes.
