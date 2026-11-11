# Repository convention verification

Local verification on 10 November 2026 for version 0.1.0. These results describe
the repository convention changes; the runtime ownership and recovery audits
remain documented under `docs/`.

## Structure and compatibility

The repository contains `.github/`, `CHANGES/`, `docs/`, `examples/`, `reports/`,
`tools/`, `src/` and `tests/`. Common root files include contribution, conduct,
security, license, changelog, Git attributes/ignore rules, MkDocs configuration,
project metadata and the uv lock. Automation lives in `tools/`; generated security
JSON and coverage output are ignored. Releases remain a manual documented process.

The project version is authoritative in `pyproject.toml`; the public runtime
version reads installed metadata. Uninstalled source explicitly reports
`0+unknown`. Wheels retain `py.typed`. Neither Redis nor aiogram-idle is required
by the base distribution. The optional combined integration is maintained in
aiogram-idle, without introducing a reverse runtime dependency.

## Checks

| Check | Result |
| --- | --- |
| Full current suite with real Redis | 342 passed; 88.79% combined line/branch coverage |
| Isolated wheel: Python 3.10.20 / aiogram 3.22.0 | Base: 276 passed, 66 explicit Redis skips; redis-py 5.0.8: 342 passed |
| Isolated sdist: Python 3.12.13 / aiogram 3.31.0 | Base: 276 passed, 66 explicit Redis skips; redis-py 7.4.1: 342 passed |
| Artifact dependency boundaries | Base installs contain neither Redis nor aiogram-idle; Redis installs still contain no aiogram-idle |
| Artifact metadata and typing | Version checks and `py.typed` checks passed outside the checkout |
| Ruff lint and formatting | Passed |
| Strict Pyright for source and examples | Zero errors |
| Strict MkDocs build | Passed |
| Wheel from generated sdist; Twine metadata checks | Passed |
| Reply, inline, command and hybrid example CLI help | Passed without `BOT_TOKEN` |
| Shared structure and whitespace | Passed |

The independent artifact environments copied tests, examples, tools and project
configuration outside the checkout. They imported the installed distribution,
not editable source. Required-Redis tests used an isolated Redis 7 container and
did not silently skip infrastructure cases. No real Telegram messages were sent.

## Security evidence

Bandit retained nine low severity findings and found no medium/high findings.
The full JSON report remains a generated artifact; the medium/high invocation
owns the CI gate. See [scan policy](README.md) for the low severity inventory.

The installed Linux development/Redis environment passed its dependency audit
(91 dependencies). An additional audit queried all 112 registry name/version
pins in the lock, including alternate platform/Python marker branches, in two
non-conflicting batches of 101 and 11 pins. No known vulnerabilities were found.
This pin audit queries advisories; it does not install every platform branch.

`pip-audit` development tooling requires Python 3.11 or newer to obtain its
patched file-locking dependency. The Python 3.10 runtime and test floor remains
supported. CI runs dependency auditing on Python 3.12.

## Limits

The complete remote CI matrix has not been executed as part of these local
checks. Python 3.11, 3.13 and 3.14 are configured in CI; the checks above do not
claim fresh execution of those environments. No package publication or deployment
was performed. External application databases and real Telegram client UX remain
outside these repository checks.
