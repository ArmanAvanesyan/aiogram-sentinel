# aiogram-kit

Independent community libraries for aiogram 3, developed in one repository.

| Distribution | Responsibility |
| --- | --- |
| aiogram-coordination | Shared application-owned isolation contracts |
| aiogram-sentinel | Middleware, throttling and error handling |
| aiogram-cmds | Command profiles and localization |
| aiogram-nav | Standalone navigation and recoverable rendering |
| aiogram-idle | Standalone inactivity lifecycle; optional Nav integration |
| aiogram-kit | Lightweight reserved umbrella package |

Each package retains its own version, dependencies, tests and release artifacts under `packages/`.
Redis and Nav integrations remain optional. Package imports are unchanged.

## Development

Run `uv lock` at the repository root. Run package commands from their package directory;
use isolated artifact environments for release verification. Package-local locks are retained
as historical verification inputs during migration, not the workspace source of truth.

## Migration status

This branch is a migration candidate. No repository has been renamed, archived or published
as part of this migration yet. See `reports/monorepo-migration/` for preservation evidence.
