# Security policy

## Reporting a vulnerability

Do not disclose vulnerabilities, credentials or exploit details in public issues.
Email the existing maintainer contact at
[arman.avanesyan@yahoo.com](mailto:arman.avanesyan@yahoo.com). Include the affected
package and version, Python/aiogram versions, a minimal reproduction and the
potential impact. Redact bot tokens, Redis URLs and personal data.

A [private GitHub security advisory](https://github.com/ArmanAvanesyan/aiogram-sentinel/security/advisories/new)
is another option when private reporting is available for the repository. If it
is unavailable, use email. Ordinary issue forms are public.

## Versions and fixes

The checkout's package version is declared in `pyproject.toml` and exported from
`src/aiogram_sentinel/version.py`. Report the exact installed version so affected
releases can be assessed. The repository does not promise backports, response
SLAs or a fixed support period. Review [release history](CHANGELOG.md) and use a
current compatible release when available.

## Application responsibilities

Sentinel provides rate limiting, debouncing and optional error handling. It does
not authenticate users, authorize application actions, sanitize arbitrary input
or guarantee protection from denial of service. Memory storage is process-local;
Redis deployments must protect their credentials and network access.

Keep dependencies updated, avoid logging message content or secrets, and configure
application access controls independently. The optional Sentry integration sends
error information to the application's configured service when enabled.

## Development checks

CI runs Bandit over library source and pip-audit over its installed runtime and
development dependencies. Reports are uploaded as CI artifacts even on scan
failure; generated JSON is not committed. These checks are point-in-time evidence,
not a guarantee that a package or application has no vulnerabilities. See
[reports/README.md](reports/README.md) for local commands.
