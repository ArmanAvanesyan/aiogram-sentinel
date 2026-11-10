# Release procedure

Release only after reviewing source, compatibility, real-Redis concurrency,
crash/loss and installed-artifact tests. Python 3.10 remains supported; audit tools
run on Python 3.11+ so patched transitive dependencies can be selected.

1. Set the version in pyproject.toml, sync the frozen lock, review Towncrier and
   render the release changelog without duplicate headings.
2. Run lint, strict typing/docs, real-Redis coverage, Bandit, dependency audit,
   wheel/sdist builds and Twine. Verify base artifacts with Redis/Idle/Nav absent.
3. Commit reviewed changes, require green candidate CI, and create a matching tag.
4. Upload the exact verified wheel, sdist and SHA256SUMS to its GitHub release.
5. Configure PyPI Trusted Publishing for this repository, `publish.yml`, environment
   `pypi`. Record the independently verified SHA256 of SHA256SUMS outside the assets.
6. Dispatch `publish.yml` against the matching version tag and pass that digest as
   `manifest_sha256`. The workflow verifies assets and publishes those exact bytes.
7. Verify PyPI hashes, fresh index installs and optional Redis imports. Publish
   Coordination before consuming Idle/Nav versions; Nav before Idle's Nav extra.

Ordinary branch pushes never publish. Do not overwrite tags or PyPI files. A bad
release requires a corrective version and, where appropriate, a documented yank.
