# Repository automation

- `check_version.py` verifies installed/project/tag identity without modifying files.
- `check_install.py` runs outside the checkout against a fresh base installation;
  pass `--redis` only for the Redis-extra profile.

Release automation lives in `.github/workflows/publish.yml` and publishes only
independently verified GitHub release assets from explicit version-tag dispatch.
