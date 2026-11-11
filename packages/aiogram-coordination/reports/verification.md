# Initial implementation verification

Verified locally on 2026-11-10 for the 0.1.0 candidate. No publication is claimed
by this report; root owns commit, remote CI, tags and publishing.

- Current source: 77 tests passed with 90.33% combined line/branch coverage against
  real Redis 7, including independent clients, renewable ownership, lease loss,
  true process SIGKILL recovery, custom isolation, Dispatcher/FSM coordination,
  full-identity normalization, external cancellation and immediate effect revocation.
- Independently installed wheel: Python 3.10.20 / aiogram 3.22.0 / redis-py 5.0.8:
  77 tests passed, 91.08% combined coverage with Redis 7.
- Independently installed sdist: Python 3.12.13 / aiogram 3.31.0 / redis-py 7.4.1:
  77 tests passed, 90.33% combined coverage with Redis 8.
- Base wheel and sdist each initialized memory scopes in a fresh environment with
  Redis, aiogram-idle, aiogram-nav and aiogram-kit absent.
- Ruff lint/format, strict Pyright, strict MkDocs, Actionlint, frozen-lock,
  version/typing/license and Twine checks passed. The wheel is built from its sdist.
- Actual Linux Python 3.12 frozen development/Redis environment: dependency audit
  zero known vulnerabilities; Bandit medium/high gate passed.
  The live source gate also passed after final scope/key hardening.
- All 119 locked registry name/version pins across Python/platform markers were
  independently audited in 106+13 non-conflicting batches: zero known vulnerabilities.
- Independent read-only review reran all 77 tests on Redis 7 and cleared the
  exact prior failure probes. Corrections cover queued acquisition and complete
  provider/Redis release tails during shutdown, immediate external-FSM lease
  revocation and explicit rejection of lossy business/destiny keys.
- The public BorrowedFsmCoordinator capability was verified through an application
  bridge that is not a concrete built-in coordinator class.

Python 3.11, 3.13 and 3.14 are configured in CI; this local report does not claim
fresh execution of every matrix entry. Memory storage is process-local; no
infrastructure failover or exactly-once external effect guarantee is made.

The final Python 3.10 cancellation provenance regression schedules an external
`cancel(None)` concurrently with FSM lease loss. Its guarded legacy marker
pin/restore matches the existing Redis cancellation logic and preserves the
external cancellation. The independent reviewer reran that minimum-profile
case and the full final suite before clearing release preparation.
