# Releasing aiogram-nav

Repository CI verifies changes; a push does not publish a package. Version 0.1.0
is currently a development distribution, not a claim of a PyPI release.
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
   uv run --no-sync towncrier build --draft --version 0.1.0
   uv run --no-sync towncrier build --yes --version 0.1.0
   uv run --no-sync python tools/check_version.py --tag v0.1.0
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

After the reviewed release commit and successful checks, the maintainer may tag
that commit, publish the verified artifacts and create matching release notes.
Confirm the destination index and artifact contents first. No credential,
repository push, tag or package upload is performed by this documentation recipe.
Use the same version in project metadata, changelog, tag and uploaded artifacts.
Finally verify installation from the chosen index and record the release outcome.
