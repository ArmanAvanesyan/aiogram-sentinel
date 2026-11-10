# Releasing

This maintainer checklist describes deliberate releases. Repository pushes and
documentation builds do not publish a package. The first release is `0.1.0`.

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
7. Publish aiogram-nav first when preparing matching releases. The optional `nav`
   extra requires a compatible aiogram-nav distribution on PyPI.
8. Create the matching GitHub release with the reviewed wheel, sdist, release
   notes and a `SHA256SUMS` manifest containing exactly those two artifact names.
   Keep the independently verified SHA256 digest of the manifest outside the
   release assets. Configure the PyPI Trusted Publisher for this repository's
   `publish.yml` workflow and `pypi` environment before dispatching publication.
9. Dispatch publication against the matching tag, using the reviewed manifest
   digest rather than a digest newly downloaded from GitHub:

   ```sh
   gh workflow run publish.yml --ref v0.1.0 -f manifest_sha256=<reviewed-manifest-digest>
   ```

   The workflow verifies tag/version equality and exact artifact filenames and
   hashes, checks metadata, and publishes those downloaded artifacts through
   PyPI Trusted Publishing. It does not rebuild or substitute distributions.
10. Verify the published file hashes and availability on PyPI. Install both the
    standalone package and `[nav,redis]` in fresh environments from the index;
    confirm the optional integration resolves without source checkouts.

Substitute the actual release version consistently. Do not add credentials,
generated security reports or build output to commits. Repository pushes never
trigger the manual publication workflow.
