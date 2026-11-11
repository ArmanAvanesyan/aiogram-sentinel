# Local review fixes

Status: verified locally, uncommitted. Package version remains 1.1.0; no release,
push, publication or deployment was performed.

## Corrections

- Hook changes update a Sentinel-owned proxy in place. Application guards and
  error middleware retain their identities/order. Unowned routers, mismatched
  installation arguments and duplicate installation are rejected. Legacy error
  defaults are consumed by the next successful setup; explicit per-setup
  configuration is recommended for multiple bots.
- Memory remains the default. Redis is a real optional extra with lazy storage
  exports, an actionable missing-extra error and a bounded redis-py range.
  Factory error messages no longer interpolate potentially sensitive URLs.
- Redis fixed-window counting and initial expiry use one atomic script. Existing
  expiry is preserved; counters lacking expiry are repaired. Public protocol
  intervals/limits reject booleans, fractions, nonpositive and out-of-range
  integers before mutation in both backends. Memory continues to use its existing
  sliding window, while Redis uses its existing fixed window; they are not
  advertised as equivalent scheduling semantics.
- Strict typing has one effective TOML configuration, typed metadata ships, and
  concrete dynamic metadata boundaries are cast explicitly. Event cleanup uses
  an owned task-forgetting API and documents that it does not cancel tasks.
- Redis tests now exercise actual public APIs against an explicitly configured
  server, use UUID namespaces, and never flush a database. Concurrent assertions
  do not rely on task completion order.
- CI runs required PR/main quality, Python/aiogram endpoint tests, real Redis and
  isolated wheel/sdist probes. Its aggregate checks actual job outcomes rather
  than emitting unconditional success summaries. Existing informational perf
  checks remain runnable locally. Documentation links/build and metadata owner
  URLs were corrected.

## Verification

- Python 3.12.13, aiogram 3.31.0: **321 tests passed** including performance tests.
- Required unit/integration suite: **308 passed, 87.31% line coverage**.
- Python 3.10.20, aiogram 3.0.0, redis-py 5.0.8: **308 passed** from the installed
  wheel, including real Redis tests.
- Real Redis 7 in a disposable local Docker container: rate/debounce concurrency,
  expiry preservation, orphan expiry repair and namespace checks passed.
- Ruff, Black, strict Pyright 1.1.405 (locked), strict MkDocs and Git diff whitespace
  checks passed. Current Pyright 1.1.414 was also checked before final lock sync.
- Wheel/sdist built; Twine 7 accepted both. Both artifacts imported in clean base
  environments without Redis or Sentry and passed memory startup, version and
  `py.typed` checks.

The configured Python 3.11/3.13 CI matrix has not been executed remotely during
this local review. Sentinel provides spam/error middleware, not idle/nav-style
leases, fencing, durable receipts or coordinated business-effect recovery.
