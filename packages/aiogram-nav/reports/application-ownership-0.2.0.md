# Application ownership and metadata migration review

The 0.2.0 implementation preserves standalone navigation and adds a shared
coordination dependency, verified application FSM borrowing, explicit manual router
placement, prepared actions, application-owned presentation and external-session
binding. Redis remains optional; Idle is not a runtime dependency.

## Verified behavior

- Application-supplied structural FSM bridges are retained. Unsupported explicit
  coordination is rejected rather than silently replaced. Live lease proof is
  required, with the backend's existing Redis fence retained.
- Manual bindings leave valid callbacks to the chosen router; stale or foreign
  reserved controls are rejected before unrelated application actions.
- Rendering receipts remain recoverable after authority revocation; cleanup only
  operates on the committed generation, and duplicate completion does not repeat it.
- Format 1 is the default. Explicit drained activation rotates the profile/history
  fence atomically, retains unresolved operations and receipts, and lazily writes
  format 2. Read-only assessment does not mutate namespace data.
- Managed Redis attestation fills only ACL-denied deployment facts. Observed unsafe
  policy/topology and connection failures still fail closed.

## Local verification

A full real-Redis 8 source run passed 382 tests with 86.38% branch-inclusive
coverage, including read-only migration assessment and explicit coordinator
selection through constructor, runtime setter and repository binding.

The final registry-only freeze independently installed the Nav wheel on Python
3.10 with aiogram 3.22 and redis-py 5.0.8, and the sdist on Python 3.12 with current
aiogram/redis-py. Each profile passed 301 standalone tests (81 Redis cases skipped),
then all 382 tests against real Redis 7, plus installed-artifact and dependency
checks. Neither environment used an adjacent checkout, source override or explicit
coordination wheel: coordination 0.1.0 resolved from PyPI with SHA256
`c3b44457924a327adf40963abcb5b6d22618539fe7968216df74b524c99f3da4`.
Standalone installs contained neither Redis nor Idle. The named test Redis instance
used a distinct local port and retained no production data.

Ruff, strict Pyright, strict MkDocs, actionlint, Bandit medium/high checks and
`git diff --check` are part of the final verification. Python compatibility CI also
covers the advertised 3.10–3.14 range, minimum/current aiogram, and Redis 7/8.

No application database/FSM migration or deployment is performed by installation.
Application session authority and business effects remain application-owned.

Coordination 0.1.0 was published through GitHub Actions run 42817944342. The
release freeze removes all candidate peer checkouts and direct wheel injection.
The uv lock resolves coordination from PyPI; Nav artifact environments must resolve
that same published dependency without adjacent repositories or source overrides.
