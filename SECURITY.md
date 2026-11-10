# Security

## Reporting a vulnerability

Do not put credentials, user message content, Redis URLs containing passwords or
exploit details in a public issue. Use GitHub's private vulnerability reporting
option if it is available for this repository. Otherwise contact the maintainer
through the contact information on the [GitHub profile](https://github.com/ArmanAvanesyan)
to arrange a private channel before sending sensitive details.

Include affected versions, a minimal reproduction, expected versus actual
authorization behavior and any proposed mitigation. This project does not promise
a response deadline or a long-term support window. The development version is
`0.1.0`; reports should identify the exact commit or installed artifact.

## Operational boundaries

Keep bot tokens and Redis credentials in application-managed secret storage.
Use isolated Redis prefixes and a supported writable primary with `noeviction`.
Redis access controls, transport security, persistence and backups belong to the
deployment. Memory storage is single-process and loses all evidence on restart.

The library coordinates conversation work and retains recovery receipts; it does
not make Telegram or application database effects exactly once. Unknown outcomes
must be reconciled with evidence. Never bypass failed ownership checks or discard
unresolved records just to allow another action.

See [Redis](docs/redis.md), [recovery](docs/recovery.md) and
[testing](docs/testing.md) for the supported failure boundaries and checks.
CI runs source scanning and dependency auditing on Python 3.12. Dependency auditing
requires Python 3.11 or newer; Python 3.10 remains supported for runtime and tests.
Generated `bandit-report.json` and `pip-audit-report.json` files are CI artifacts,
not committed baselines or proof that a deployment is secure.
