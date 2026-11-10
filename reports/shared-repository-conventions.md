# Shared repository conventions: local verification

Date: 2026-11-10. Scope: aiogram-cmds repository conventions and the previously
reviewed local fixes. Version remains 0.1.1; runtime dependency floors and license
are unchanged. No commit, push, tag, deployment or publication was performed by
this verification agent.

## Changes

- Repository automation lives in `tools/`; generated security JSON is ignored
  rather than committed. Added line-ending conventions and retained maintained
  reports separately from build output.
- CI has required quality, coverage, minimum/current aiogram and artifact checks;
  security scans retain their actual exit status and upload reports. Pages
  deployment is manual opt-in. Changelog checking uses read-only pull requests.
- `docs/releasing.md` is canonical, with compatibility links at old locations.
  Contribution, security and community guidance describes actual capabilities.
- Four runnable examples create bots/logging only from their entry points,
  propagate errors, close sessions and use actual application-selected profiles.
  Removed documentation for nonexistent examples and nonexistent `Flags.user_id`.
- Real example execution uncovered an adapter mismatch: aiogram uses
  `I18n.use_locale`, while custom adapters may expose `with_locale`. Both work.
  Tests compile gettext catalogs and exercise real Dispatcher updates through a
  fake Telegram session. Minimum aiogram uses explicit session cleanup because
  its Bot does not support the newer async context-manager interface.

## Verification

- Python 3.12.13 / aiogram 3.31.0: **252 unit/integration tests passed**,
  **97.48% line coverage** (required threshold: 80%). Full suite including
  performance tests: **262 passed**.
- Python 3.10.20 / aiogram 3.0.0: **252 unit/integration tests passed**, including
  the compiled-gettext scenario (Babel installed as optional test support).
- Ruff lint/format, strict source Pyright, strict MkDocs, actionlint and whitespace
  checks pass.
- Configured Bandit scan passes. The refreshed locked environment has **zero
  known vulnerabilities** in pip-audit at verification time; this is a snapshot,
  not a guarantee about future advisories.
- Wheel and sdist builds and Twine checks pass. Both artifacts install and import
  outside the checkout, report matching metadata/runtime versions and contain
  `py.typed`, with Redis, aiogram-idle and aiogram-nav absent.
- Included gettext catalogs compile; generated `.mo` files remain ignored.

Remote GitHub workflows, other operating systems and the complete configured
Python/PyPy matrix were not executed locally. Telegram tests use controlled
sessions and do not contact Telegram. No release tag was created.
