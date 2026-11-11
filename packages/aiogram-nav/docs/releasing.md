# Releasing aiogram-nav

Repository CI verifies changes; a push does not publish a package. Version 0.3.0
is the initial alpha release.
Publication requires a separate maintainer decision, working credentials and
review of the artifacts being released.

## Prepare

1. Review the intended commits and resolve security, compatibility and recovery
   concerns. Keep optional aiogram-idle integration outside mandatory dependencies.
2. Set the next version in `pyproject.toml`, the authoritative version source.
   Refresh the editable installation with `uv sync --extra redis`; runtime version
   reads installed distribution metadata. An uninstalled source tree reports
   `0+unknown`, not a guessed release version.
3. Review the Towncrier draft and consume the release fragments only when ready:

   ```sh
   uv run --no-sync towncrier build --draft --version 0.2.0
   uv run --no-sync towncrier build --yes --version 0.2.0
   uv run --no-sync python tools/check_version.py --tag v0.2.0
   ```

   Substitute the actual version consistently. The non-draft command updates
   `CHANGELOG.md` and removes consumed fragments; inspect that diff.

## Verify the exact candidate

Follow [CONTRIBUTING.md](https://github.com/ArmanAvanesyan/aiogram-nav/blob/main/CONTRIBUTING.md) and require successful CI quality,
compatibility, real-Redis and security jobs. Run strict documentation and typed
source/example checks. Record which platform/dependency combinations were
actually executed; configured CI jobs are not local evidence.

```sh
uv build
uv run --no-sync twine check dist/*
```

Use a clean artifact output directory so stale versions cannot be uploaded.
Install each wheel and sdist into a fresh environment outside the checkout.
Copy `tools/check_install.py` there and run it to verify version agreement,
typed markers and memory initialization with Redis and aiogram-idle absent.
Repeat with the Redis extra and `--redis`, plus the full real-server tests.
CI performs these isolated checks; see [tools](https://github.com/ArmanAvanesyan/aiogram-nav/blob/main/tools/README.md).

## Publish deliberately

Commit the reviewed release changes and require successful CI before tagging.
Build and verify the candidate from that exact source. Configure the PyPI Trusted
Publisher for this repository, workflow `publish.yml` and environment `pypi`.
The workflow is manual and tag-only; ordinary pushes and releases never publish.

Create a checksum manifest for the two verified files, upload those exact bytes
to the matching GitHub release, then dispatch publication with the independently
verified manifest digest. For example, after preparing reviewed release notes:

```sh
git tag -a v0.2.0 -m "Release 0.2.0"
git push origin v0.2.0
(cd dist && shasum -a 256 *.whl *.tar.gz > SHA256SUMS)
gh release create v0.2.0 dist/*.whl dist/*.tar.gz dist/SHA256SUMS \
  --verify-tag --notes-file release-notes.md
manifest_sha256=$(shasum -a 256 dist/SHA256SUMS | cut -d ' ' -f 1)
gh workflow run publish.yml --ref v0.2.0 -f manifest_sha256="$manifest_sha256"
```

Substitute the intended version and candidate directory. The workflow checks tag,
filenames, manifest and distribution digests before publishing through OIDC; it
does not rebuild the reviewed distributions. Require the workflow to succeed,
then verify availability and fresh standalone installation from PyPI. Publish
aiogram-nav before aiogram-idle when releasing the compatible pair, so Idle's
optional `nav` dependency resolves. Record the release outcome and never replace
already published version files.

## Registry-only dependency freeze

Nav 0.2.0 requires the published `aiogram-coordination>=0.1.0,<0.2` distribution.
Release CI uses the registry lock without adjacent checkouts or uv source overrides.
Wheel and sdist probes resolve coordination from PyPI, first without Redis or Idle,
then with the Redis extra against a real server. These indexed probes must pass
before tagging or publishing; a direct candidate wheel is not a substitute.
