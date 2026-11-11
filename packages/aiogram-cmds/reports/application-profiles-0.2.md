# aiogram-cmds 0.2.0 implementation verification

Verified locally on 2026-11-10. Publication, release tags, PRs and remote CI are
owned by the coordinating agent; this report does not claim they have occurred.

## Changes

- Separate rendering `language` from Telegram `language_code`: omission preserves
  language-specific behavior unless configuration explicitly disables it; `None`
  omits the API field and targets the default-language fallback.
- Add global and per-scope `per_language`, explicit obsolete-language cleanup,
  and a migration guide explaining remaining language-specific overrides.
- Add immutable `CommandApplyResult`/`CommandBatchResult`, `apply_profile`,
  `apply_all`/`apply_config_result`, caller-owned SHA256 confirmation fingerprints,
  and partial-target evidence. Existing wrappers retain Boolean or None returns.
- Confirm only literal True SDK responses. Failures and ambiguous responses never
  confirm hashes; cancellation propagates. Invalid cleanup lists and hashes are
  rejected before effects. Existing flag APIs remain compatibility helpers.
- Test real compiled English/Russian/Armenian catalogs and locale restoration.
- Add a network-free runnable application-profile example and installed-artifact
  CI checks at minimum/current aiogram endpoints.
- Project metadata and runtime version are 0.2.0. Redis remains a client-only
  optional extra; base installs include neither Redis, Idle nor Nav.

## Verification

- Full current suite: **299 passed**, **94.32% line coverage**; required
  unit/integration suite: **289 tests**.
- Fresh wheel/Python 3.10.20/aiogram 3.0.0 and fresh sdist/Python 3.12.13/aiogram
  3.31.0: required suites run outside the checkout, along with typed/version/base
  dependency checks, pip compatibility checks and dry-run example execution.
- Ruff lint/format, strict Pyright, strict MkDocs, Actionlint, version consistency,
  frozen lock, Bandit and whitespace checks pass.
- The frozen Python 3.12 Linux development environment passed dependency audit
  and Bandit with zero findings; strict documentation and the then-current
  285-case required suite passed in the Linux container. The final small response
  guard regression adds four tests; final remote CI owns the full Linux rerun.
- Wheel and sdist builds and Twine metadata checks pass. Candidate artifacts:
  `/tmp/aiogram-cmds-020-candidate-final/`. Root must assemble the reviewed release
  changelog and rebuild exact release bytes after committing the release source.

The candidate artifact tests do not install Redis, Idle or Nav, do not send real
Telegram requests, and do not claim cross-replica command-cache guarantees.
Configured Python/platform CI jobs are not evidence of fresh local execution.
