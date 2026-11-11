# Repository alignment verification

The repository adopts the common aiogram-library contribution, documentation,
packaging and verification conventions while preserving its standalone runtime,
optional Redis backend and optional navigation integration. No package release,
version bump or deployment is part of this change.

## Runtime baseline

Before packaging/documentation changes, the current implementation passed all
**508 tests** with **89.27% combined line/branch coverage** on Python 3.12.13,
aiogram 3.31.0, redis-py 7.4.1 and an isolated Redis 7 server. The command was:

```sh
AIOGRAM_IDLE_REDIS_URL=redis://127.0.0.1:16482/0 \
AIOGRAM_IDLE_REQUIRE_REDIS=1 \
  .venv/bin/python -m pytest --cov=aiogram_idle \
    --cov-config=coverage-nav.toml --cov-report=term-missing
```

This includes real-Redis concurrency, lease/crash recovery, callback ownership,
FSM coordination and optional-navigation cases. All tests passed in 338.77 seconds.
Ruff lint/format and both strict Pyright profiles also passed. The ordinary and
optional-navigation examples compile and show CLI help without a bot token.

## Boundaries

No live Telegram messages or external application business effects were executed.
Memory storage remains single-process and non-durable. Redis persistence and
failover qualification remain deployment responsibilities. Optional navigation
still belongs to `aiogram_idle.integrations.nav`; neither standalone base install
nor Redis-only install requires aiogram-nav.

Historical matrix evidence is retained in `docs/verification.md`; it is not a
claim that every historical endpoint was rerun for repository-convention changes.
Generated dependency and static-security JSON reports belong in CI artifacts,
not tracked source.

## CI and security verification

CI retains standalone quality, Python/aiogram endpoints, Redis server/client
endpoints and isolated artifact checks. Strict documentation and source/dependency
security checks are required. A separate automatic navigation job checks out the
peer repository explicitly; standalone jobs neither install nor check out Nav.
The manual peer-revision workflow remains available for the broader optional
matrix. Required-job aggregation fails for failed, cancelled or skipped jobs.

Both workflow files parse as YAML, and every multiline shell step passes
`bash -n`. Source Bandit scanning passes with no findings. Twenty `B101` sites
have individual suppressions and adjacent explanations: they assert internal
reserved-operation/type invariants after explicit ownership checks or internal
reducer construction, rather than validating external input or authorization.
No assert suppression applies globally and no runtime behavior changed.

Installed dependency auditing passes. An additional audit exported the frozen
Redis/development dependency set and queried **all 119 pinned Python/platform
variants**, removing environment markers and grouping duplicate package names
into separate input files. Both groups (106 and 13 pins) report no known
vulnerabilities. This caught vulnerable Python-3.10-only `filelock` versions that
an audit of the current Python 3.12 environment could not see.

The corrected development marker makes `pip-audit` available on Python 3.11 or
newer, allowing its transitive `filelock` dependency to resolve the fixed 4.2.10
release. Downgrading to 3.x did not clear the advisories and was rejected. This
does not change Python 3.10 runtime support; security automation runs on 3.12.
Ruff lint/format, strict core Pyright and frozen-lock validation pass after these
comment/tooling-only changes. Remote workflow execution is not claimed here.

## Final examples and artifacts

The final focused suite passed **18 cases** on both Python 3.12 / aiogram 3.31.0
and Python 3.10 / aiogram 3.22.0. It covers all four ordinary-handler/FSM prompt
styles, all four optional navigation styles through `Dispatcher.feed_update`,
token-free CLI help, import-time logging isolation and distribution metadata.
The optional example now uses global INFO with package-scoped DEBUG instead of
enabling DEBUG for every dependency. Missing credentials produce startup guidance.
`examples/README.md` explains execution, persistence boundaries and credential handling.

Final Ruff lint/format, both strict Pyright profiles, strict MkDocs and frozen-lock
checks passed. Final wheel/sdist builds and Twine checks passed. Each artifact
installed independently into a clean environment and verified the typed marker,
metadata version and core imports with Redis and aiogram-nav absent. The sdist
contains maintained guides, examples and community policies and excludes generated
security reports and documentation output. No full runtime suite was repeated
after comment, metadata, documentation and example-only changes; the 508-case
runtime baseline above and final focused runs are reported separately.

## Documentation and community conventions

Added contributor, security and conduct guidance, portable checkout installation
recipes, and a strict MkDocs site covering installation, quickstart, typed API
groups, architecture, testing/compatibility and manual releasing. Existing recovery,
Redis and navigation guides remain the detailed behavioral references. Current
guidance now reflects the implemented optional navigation module; historical
memory/Redis audits are explicitly labeled as phase-specific evidence.

`uv run --no-sync mkdocs build --strict` passed. MkDocs resolved the site's local
navigation and documentation links without warnings. No release, response SLA,
private-reporting feature enablement or package-index availability was claimed.
