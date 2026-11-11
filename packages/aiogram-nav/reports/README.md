# Verification evidence and generated reports

Maintained review reports may be committed here. Generated machine output stays
out of Git: CI uploads `bandit-report.json` and `pip-audit-report.json` as artifacts;
local copies are ignored.

Run the same security checks locally:

```sh
uv sync --frozen --extra redis --python 3.12
uv run --no-sync bandit -r src -f json -o bandit-report.json --exit-zero
uv run --no-sync bandit -r src -ll
uv run --no-sync pip-audit --format=json --output=pip-audit-report.json
```

The first Bandit command records every severity and deliberately does not own the
pass/fail result. The second command fails on medium/high severity findings.
Review low severity findings in the full artifact; no test IDs are suppressed.
The initial inventory contains eight B101 internal invariant/type-narrowing
assertions and one B110 diagnostic-checkpoint fallback that preserves the original
exception after an interrupted effect. These are not substitutes for public input
validation, authorization, ownership checks or durable effect evidence.

`pip-audit` fails on known dependency vulnerabilities in the resolved development
and Redis-enabled environment. It cannot audit unpublished project metadata
against the advisory registry; it does inspect registry dependencies. An empty
advisory result does not establish that the application or dependencies are safe.

Run security tooling on Python 3.11 or newer (CI uses Python 3.12).
`pip-audit` is a development-only dependency on those Python versions: its current
patched dependency chain is not available on Python 3.10. Python 3.10 remains
supported for the runtime and compatibility tests. The lock therefore avoids
retaining the vulnerable historical filelock dependency on Python 3.10; current
security environments resolve patched filelock 4.2.10.

The 10 November 2026 local check also installed the frozen development and Redis
dependency export in a disposable Python 3.12 Linux container: 91 dependencies
were audited with no known vulnerabilities. The lock uses cryptography 50.0.2
and pip 26.3; macOS-only audits do not verify Linux marker branches.

A subsequent advisory check queried all 112 registry package/version pins in
`uv.lock`, including alternatives selected by other Python/platform markers.
Two batches (101 and 11 pins, without duplicate names in a batch) passed with no
known vulnerabilities. Python 3.10 compatibility tests remain supported; the
audit tool runs on Python 3.11+ so its dependency chain uses patched filelock
4.2.10 rather than the vulnerable older-Python releases.

The CI `Required checks` job fails when any quality, compatibility, Redis or
security job fails, is cancelled or is skipped. CI performs no release or package
publication on a push.
