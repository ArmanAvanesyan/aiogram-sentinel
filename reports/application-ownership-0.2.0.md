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
selection through constructor, runtime setter and repository binding. Redis 7 artifact verification passed all 382 tests per profile
for a Python 3.10 / aiogram 3.22 / redis-py 5.0.8 wheel and a Python 3.12 / current
aiogram / current redis-py sdist, including standalone installs without Idle or Redis
and subsequent Redis-enabled runs. Both profiles used the final coordination
wheel (SHA256 `c3b44457924a327adf40963abcb5b6d22618539fe7968216df74b524c99f3da4`).
After the final live repository-selection guard, rebuilt wheel/sdist installs also
passed the 18 focused application/session/isolation regressions. Final release
artifacts must be rebuilt against the published coordination dependency.

Ruff, strict Pyright, strict MkDocs, actionlint, Bandit medium/high checks and
`git diff --check` are part of the final verification. Python compatibility CI also
covers the advertised 3.10–3.14 range, minimum/current aiogram, and Redis 7/8.

No application database/FSM migration or deployment is performed by installation.
Application session authority and business effects remain application-owned.

Coordination's reviewed source and tag are public, but PyPI publication still needs
owner authentication. Candidate CI pins that exact public source and builds a
normal peer wheel for artifact probes. It deliberately retains the development uv
source override. Registry-only locks and clean-index artifact verification remain
a release gate after coordination reaches PyPI; candidate CI does not bypass it.
