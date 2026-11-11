# Security policy

This repository is developing the 0.1 series. Report security issues against the
current source revision; older development snapshots have no separate patch
support commitment. No response-time or remediation SLA is promised.

## Reporting a vulnerability

Do not open a public issue containing an exploit, credentials, bot tokens,
conversation content or private Redis URLs. If GitHub private vulnerability
reporting is available, use
[Report a vulnerability](https://github.com/ArmanAvanesyan/aiogram-nav/security/advisories/new).
If it is unavailable, contact the maintainer privately at
[arman.avanesyan@yahoo.com](mailto:arman.avanesyan@yahoo.com).

Include the affected revision/version, Python and aiogram versions, backend,
reproduction steps and expected/observed ownership or recovery behavior. Use
synthetic actors and sanitized configuration. Coordinate disclosure privately
until the impact and mitigation have been assessed.

Review [runtime security boundaries](docs/security.md) and
[scan/report policy](reports/README.md) before deploying a consuming application.
Memory storage is non-durable. Redis durability and access control are application
deployment responsibilities. Unknown external effects require explicit recovery;
a lease cannot retract a Telegram request already accepted by the server.
