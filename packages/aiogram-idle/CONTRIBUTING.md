# Contributing

Explain the problem in an issue or pull request and include a minimal reproduction
for bugs. Keep library behavior independent of a consuming bot's business flows.
Follow the [code of conduct](CODE_OF_CONDUCT.md) and use the
[security reporting guidance](SECURITY.md) for sensitive findings.

## Development

Use Python 3.10 or newer. From the checkout:

```sh
uv sync --frozen --extra redis --python 3.12
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync pytest
uv run --no-sync mkdocs build --strict
```

Tests requiring a real Redis server are skipped without its URL. For storage,
recovery or coordination changes, run the required real-server suite as described
in [testing](docs/testing.md). Use a dedicated server because tests may flush the
script cache. Never use production Redis or real Telegram credentials in tests.

Optional navigation tests require the adjacent compatible `aiogram-nav` checkout
and `uv sync --frozen --extra nav --extra redis`. Standalone changes must continue
working without that peer. The [navigation guide](docs/navigation.md) explains
the separate type and coverage profiles.

## Change conventions

- Keep public interfaces typed and include behavior-focused regression tests.
- Preserve operation receipts, ownership checks and uncertain-effect evidence.
- Add a [Towncrier fragment](CHANGES/README.md) for user-visible changes.
- Document compatibility and recovery changes alongside the public behavior.
- Keep repository automation in `tools/`; do not commit generated audit reports,
  build output, credentials or local environment files.

See [testing](docs/testing.md), [repository tools](tools/README.md) and the
[maintainer release process](docs/releasing.md) for verification commands.
