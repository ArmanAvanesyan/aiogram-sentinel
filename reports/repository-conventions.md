# Repository convention verification

Verified locally on 2026-11-10. Package version remains 1.1.0 and the existing
MIT license is unchanged. This report records local checks; it does not claim
remote CI, publication or deployment.

## Changes

- Repository automation lives in `tools/`, including the isolated-install probe.
  LF attributes, generated-output ignores and a locked Towncrier development
  dependency support reproducible contribution and release preparation.
- `docs/releasing.md` is canonical; the old release page links to it. Contributor,
  security and community documents describe actual responsibilities without
  invented service promises. Public issue forms no longer request confidential
  vulnerability details.
- Required CI includes lint, formatting, strict typing, strict documentation,
  real-Redis tests, minimum/latest aiogram endpoints, artifact installs, changelog
  validation and security scans. Generated JSON belongs in CI artifacts rather
  than source control. Privileged PR labeling never executes contributor code.
- Vulnerable locked dependencies were updated within existing requirements.
  Compatible MkDocstrings versions support the patched documentation stack.
- The runnable example registers its handlers on the protected router, uses
  valid Telegram calls and configures safe development logging only when run.
  Dispatcher tests check rate limiting, debounce and friendly error handling.

## Local evidence

- Python 3.12 / aiogram 3.31: full suite **325 passed** with **87.76%** line
  coverage, including Redis 7 concurrency/expiry tests. The required
  unit/integration subset contains 312 tests; 13 additional tests exercise
  performance behavior. All four example integration tests also pass against
  installed minimum aiogram 3.0 on Python 3.10.
- Ruff, Black, strict Pyright, strict MkDocs, Actionlint, lock consistency,
  Towncrier draft and whitespace checks passed.
- Bandit: zero findings. pip-audit: zero known vulnerabilities in the installed
  locked runtime/development environment at verification time.
- Wheel and sdist built successfully; Twine accepted both. Base-distribution
  probes verify memory startup, version equality and `py.typed` without requiring
  Redis or Sentry.

Python/platform CI matrices are configured but have not been executed remotely
as part of this local verification. Security scans are point-in-time evidence.

## Linux CI follow-up

The first remote Linux run exposed two gaps in the local evidence: Linux-only
`cryptography` 46.0.2 had seven advisories, and Sentry type-guard assertions were
reported by Bandit. The lock now resolves cryptography 50.0.2, and explicit
runtime guards replace the assertions without suppressing the scan. A fresh
Python 3.12 Linux container installed the frozen all-extras graph and passed
both Bandit and pip-audit with zero findings.

The minimum-aiogram job previously replaced one package inside a locked graph,
leaving a pytest-asyncio/typing-extensions incompatibility. Endpoint jobs now
solve fresh complete environments. The minimum profile uses pytest-asyncio<1
to respect aiogram 3.0's typing-extensions<4.8 requirement. The exact profile
passed **315 unit/integration tests** with real Redis on Python 3.10, with
**90.37%** coverage. The independent frozen development environment remains
the security-audit target.
