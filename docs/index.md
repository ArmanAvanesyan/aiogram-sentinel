# aiogram-kit

Community libraries for aiogram 3, developed together and installed independently.

| Package | Responsibility | Documentation |
| --- | --- | --- |
| aiogram-coordination | Shared application-owned isolation contracts | [Guide](libraries/aiogram-coordination/README.md) |
| aiogram-sentinel | Throttling, debounce and error handling | [Guide](libraries/aiogram-sentinel/README.md) |
| aiogram-cmds | Localized commands and application-selected profiles | [Guide](libraries/aiogram-cmds/README.md) |
| aiogram-nav | Navigation and recoverable rendering | [Guide](libraries/aiogram-nav/README.md) |
| aiogram-idle | Inactivity prompts and recovery | [Guide](libraries/aiogram-idle/README.md) |

Install only the packages you need. Redis is optional. Idle and Nav each work independently;
Idle's `nav` extra enables their optional integration. Coordination remains a separate distribution.
The `aiogram-kit` distribution currently carries a version marker without installing the libraries.

See [standalone Idle](standalone-idle.md), [standalone Nav](standalone-nav.md), and
[monorepo development and independent releases](monorepo.md).

This community project is not affiliated with the aiogram maintainers. Package-owned documentation
is included directly from its source during site builds; the original Kit design documents remain preserved.
