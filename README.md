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

## Migration evidence

History, document and GitHub-record mappings and archival gates are recorded under
`reports/monorepo-migration/`. Cross-library benchmark tools live under `tools/optimization/`;
package-owned drivers and tests remain with their distributions.

This community project is not affiliated with the aiogram maintainers.
