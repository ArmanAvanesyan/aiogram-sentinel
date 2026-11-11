# Security

## Reporting a vulnerability

Do not disclose bot tokens, credentials, private messages or exploit details in
public issues. Use [GitHub private vulnerability reporting](https://github.com/ArmanAvanesyan/aiogram-cmds/security/advisories/new)
if it is enabled for this repository. If unavailable, contact the maintainer at
arman.avanesyan@yahoo.com, the contact already published in this repository.

Include the affected version, a minimal reproduction, expected impact and any
mitigation. Remove credentials and personal data from logs and examples. No
response-time guarantee or supported-version security window is currently defined.

## Application responsibilities

Command visibility is not authorization. Validate permissions in each protected
handler. Applications own authentication, secrets, persistence and coordination
between workers. The Redis extra installs a client only; it does not implement a
distributed backend or make Telegram command updates atomic.

CI runs Bandit against package sources and pip-audit against the locked development
environment. Findings fail their jobs and JSON outputs are uploaded as CI artifacts;
generated reports are not committed. Passing scans do not guarantee that a package
or consuming application is free of vulnerabilities.
