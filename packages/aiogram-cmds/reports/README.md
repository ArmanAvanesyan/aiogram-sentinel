# Maintained reports

This optional directory is for reviewed, human-maintained verification evidence.
Current package verification is documented in [docs/verification.md](../docs/verification.md).

Coverage, benchmark and security scan outputs are generated locally or uploaded
as CI artifacts. They are ignored rather than committed. In particular,
`bandit-report.json` and `pip-audit-report.json` are not repository source files.
Never include credentials, Telegram messages or other private data in reports.
