# Security policy

Report vulnerabilities privately to [arman.avanesyan@yahoo.com](mailto:arman.avanesyan@yahoo.com)
or use a [private GitHub advisory](https://github.com/ArmanAvanesyan/aiogram-kit/security/advisories/new)
when private reporting is available. Ordinary issues are public. Include the exact affected
distribution/version, Python/aiogram versions, impact and a minimal reproduction. Redact bot
tokens, Redis credentials, message content and personal data.

Each distribution has its own version and changelog under `packages/`. The repository does not
promise backports, response SLAs or a fixed support period. Use a current compatible release.

Applications own authentication, authorization and infrastructure security. Preserve the libraries'
documented callback/session ownership and coordination guards. Memory storage is process-local;
protect Redis credentials, network access and persistence as documented. Sentinel's optional
Sentry integration sends information to the application's configured service when enabled.

CI preserves package-specific security scans and dependency audits. These provide point-in-time
evidence, not a guarantee that a package or application has no vulnerabilities. See the package
security policies and reports for local commands and integration-specific responsibilities.
