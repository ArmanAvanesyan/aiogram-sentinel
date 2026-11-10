# Releasing

This is a maintainer checklist, not an automatic publishing workflow. The current
development version is `0.1.0` and has not been published to PyPI. Repository pushes
and documentation builds do not publish a package.

1. Review compatibility, recovery/storage schema changes and dependency boundaries.
   Check the supported Python/aiogram and real-Redis jobs, plus optional navigation
   integration against a compatible peer revision.
2. Review the fragments in `CHANGES/`. Preview with
   `uv run --no-sync towncrier build --draft --version 0.1.0`, substituting the
   intended release version when preparing a future release.
3. Set the intended version in `pyproject.toml`, the authoritative source. Runtime
   version reporting reads installed distribution metadata. Refresh `uv.lock` and
   sync the environment before checking the version.
4. Run the [quality, security and artifact checks](testing.md), including
   `uv run --no-sync python tools/check_version_tag.py`. Review dependency audits
   on Python 3.11+ and resolve findings rather than committing an ignored baseline.
5. Assemble the changelog with Towncrier only after reviewing its draft, then
   rebuild wheel/sdist and verify their metadata and isolated installations.
6. Commit the reviewed release changes. Create a matching tag only when a release
   is authorized; the version tool checks `GITHUB_REF` when run on a tag.
7. Publish the verified artifacts only through a separately configured and
   authorized package-index process. Verify availability and install from that
   index before advertising installation instructions for the released version.

The optional `nav` extra requires a compatible aiogram-nav distribution on the
target package index. Until that is available, use the documented source/checkout
installation; do not assume a GitHub push satisfies that dependency on PyPI.
Do not add credentials, generated security reports or build output to commits.
