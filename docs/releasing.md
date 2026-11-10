# Releasing

This page describes the maintainer procedure implemented by
[the release workflow](https://github.com/ArmanAvanesyan/aiogram-sentinel/blob/main/.github/workflows/release.yml).
It does not create or authorize a release. Branch pushes and pull requests run
verification; only an explicit `vMAJOR.MINOR.PATCH` tag triggers publishing.

## Prepare a release

1. Review the changes and compatibility impact. Choose the next version; do not
   bump it solely to align repository structure.
2. Synchronize the development environment with `uv sync --frozen --all-extras`.
3. Run the checks in [verification](TESTING.md), including real Redis tests and
   dependency-isolated wheel/sdist installation. Review the CI security artifacts.
4. Update both `pyproject.toml` (`project.version`) and
   `src/aiogram_sentinel/version.py` (`__version__`). Update `uv.lock` using
   `uv lock`, then verify a frozen sync still succeeds.
5. Review the Towncrier fragments and draft the changelog for the chosen version.

```bash
uv run --no-sync towncrier build --draft --version X.Y.Z
```

Fragments live directly in `CHANGES/` and use the `.rst` types `feature`, `bugfix`,
`doc`, `removal` or `misc`. See
[fragment guidance](https://github.com/ArmanAvanesyan/aiogram-sentinel/blob/main/CHANGES/README.md).
Once reviewed, run `uv run --no-sync towncrier build --version X.Y.Z` and commit
the resulting `CHANGELOG.md` and consumed-fragment changes with the version update.
Check version equality without creating a tag:

```bash
GITHUB_REF=refs/tags/vX.Y.Z uv run --no-sync python tools/check_version_tag.py
uv build
uv run --no-sync python -m twine check dist/*
```

`X.Y.Z` is a placeholder for the selected release version, not a shell variable.
Do not reuse a version already published to PyPI.

## Tag and publish

After the release commit and required CI checks are approved, the maintainer can
create and push its matching `vX.Y.Z` tag. The tag workflow validates version
consistency, builds wheel/sdist artifacts, checks them with Twine, publishes
through the configured PyPI environment and attaches artifacts to a GitHub
release with generated notes.

The `pypi` environment and trusted-publishing binding must already be configured
for publishing to succeed. This documentation does not assert that remote
credentials, environment approvals or PyPI settings have been verified. A normal
branch push neither creates a tag nor publishes a package.

## After publishing

Confirm the workflow outcome, artifact versions and installation from the
published distribution. Report compatibility changes in the changelog and user
documentation. For a defective release, assess a corrective release or yanking
rather than deleting history. See
[security policy](https://github.com/ArmanAvanesyan/aiogram-sentinel/blob/main/SECURITY.md)
for private vulnerability reporting.
