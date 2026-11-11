# aiogram-kit

Community libraries for aiogram 3, developed in the [aiogram-kit monorepo](https://github.com/ArmanAvanesyan/aiogram-kit).

This distribution is a lightweight reserved umbrella: it provides a version marker and installs
none of the libraries automatically. Install only the distributions you need:

| Distribution | Responsibility |
| --- | --- |
| aiogram-coordination | Shared application-owned isolation contracts |
| aiogram-sentinel | Middleware, throttling and error handling |
| aiogram-cmds | Localized commands and application-selected profiles |
| aiogram-nav | Standalone navigation and recoverable rendering |
| aiogram-idle | Standalone inactivity lifecycle and optional Nav integration |

Redis support is optional. Nav does not require Idle, and Idle's base installation does not
require Nav. Their shared coordination contracts remain a neutral independent package.

See the [documentation](https://armanavanesyan.github.io/aiogram-kit/) for installation,
standalone examples, optional integration, development and independent release procedures.
Existing package names and Python imports are unchanged by the repository migration.

This community project is not affiliated with the aiogram maintainers.
