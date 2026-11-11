# Repository tools

Run these tools from the repository root with the locked development environment:

```sh
uv run --no-sync python tools/check_version.py
uv run --no-sync python tools/check_version.py --tag v0.1.0
```

`check_version.py` compares the authoritative project version with installed
metadata and the public runtime export. The optional explicit tag check is useful
before releasing; it never creates tags or invokes Git.

`check_install.py` verifies an artifact installed into an isolated environment.
Copy it outside the checkout and run it with that environment's Python. Base
checks require Redis and aiogram-idle to be absent; `--redis` instead requires
the Redis client. It performs no network calls or Telegram requests.

Build wheel and sdist with `uv build`, validate them with
`uv run --no-sync twine check dist/*`, then install each into a fresh environment
before running `check_install.py`. CI exercises this boundary automatically.

Generated coverage and security reports belong in local ignored output or CI
artifacts. This directory contains source-controlled automation, not scan output.
