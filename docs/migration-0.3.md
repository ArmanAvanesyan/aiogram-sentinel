# Storage format 3 and explicit engine selection

The default engine remains Python. `IdleConfig(engine="rust")` requires the exact
`aiogram-idle-native==0.3.0` companion, ABI 1. Selection checks the complete native
interface before creating a backend or initializing a Redis namespace. A missing,
incompatible or unloadable companion raises `ConfigurationError`; runtime failures
never switch engines after a mutation. Python and Rust use the same storage protocol.
The companion performs deterministic computation only; Python retains I/O, locking,
authorization, Telegram delivery and application callbacks. Installing the base
package does not install Rust, Redis or navigation.

The 0.3.0 native companion is source-only and withheld from PyPI/tags. The serial
representative CPU gate measured about 6.6% more process CPU for Rust, failing the
required 20% reduction. Redis tails were near parity; unstable repeated tail
measurements do not establish an improvement. Keep the default Python engine.
Native functional CI and source builds remain available for investigation.

The native companion has a separate release workflow. Availability and performance
qualification are separate gates: a local source build is not evidence of a PyPI
release or a measured speedup. Development builds can use `uv pip install ./native`
with Rust and Maturin build prerequisites installed.

## New applications

Use `MemoryIdleBackend(storage_format=3)` or
`RedisIdleBackend(redis=client, storage_format=3)` explicitly. Redis format 3 bootstrap
atomically establishes its namespace history and format marker. It refuses a legacy
namespace rather than upgrading it implicitly. Omitting the constructor option
preserves the existing/default format behavior.

Format 3 keeps current state separate from pending recovery and individual completed
receipts. Redis completed receipts are physical string keys with server-time anchored
absolute expiry; pending and uncertain evidence has no automatic TTL. Immutable,
content-addressed result blocks preserve exact original generic component results.
Repeated operation IDs return the original accepted result during the replay window,
without renewing that window. `replay_retention_seconds=None` inherits
`recovery_retention_seconds`; an explicit positive value changes completed receipt
retention independently. Expired receipts may be removed during a live session.
Pending or uncertain effects and unexpired promised receipts are never evicted to
admit new work. Admission fails with `Overloaded` instead.

A string operation ID cannot establish its own history indefinitely. After the
advertised replay window, lookup may return `unknown_history`; callers must
revalidate application state before an explicit retry. Automatic recovery never
turns unknown history into permission to repeat a business action.

## Existing Redis applications

1. Stop incoming admission and drain workers and protected handlers. Remove all old
   writers. Keep the shared FSM isolation and Redis connection alive while draining.
2. Back up Redis and inspect unresolved effects. If starting from format 1, complete
   the documented format 2 activation first.
3. Inspect `activate_storage_format(expected=2, target=3, operation_id=...,
   old_workers_drained=True, dry_run=True)`, then repeat with `dry_run=False` using
   the same operation ID. Activation changes the writer/history fence; it does not
   extend authentication or effect deadlines.
4. Page through `migrate_storage_records(cursor=..., limit=32, dry_run=True)`, then
   execute the same effect-free migration with `dry_run=False`. Continue until its
   cursor is `"0"`. A large individual record may require more than one page.
5. For an existing combined navigation component, explicitly page
   `integration.navigation_repository.migrate_canonical(nav_key, limit=32,
   dry_run=False)` until `done`. Dry-run inspection is available first. This
   preserves navigation's canonical operation evidence and first accepted Idle
   activity result. A legacy component is not silently converted by a handler.
6. Verify unresolved evidence and exact replay results before admitting new work.
   Rollback after activation requires a compatible reader or an explicit coordinated
   repair, not restarting a legacy writer.

Migration keeps the original source unchanged through bounded copy and verification
pages, followed by a fenced atomic cutover. It preserves original absolute terminal
expiry and persistent unresolved evidence. One immutable original envelope backup
is retained per conversation. A source containing opaque components or unknown
retention is conservatively persistent; temporary migration space therefore includes
that original envelope as well as staged rows. This is migration evidence, not a
second runtime operation ledger. Missing promised rows fail closed; the library
never restores a whole old backup over newer writes.

`inspect_migration_backup`, `list_migration_backups` and
`export_migration_backup(expected_digest=...)` support operator inspection.
`cleanup_migration_backup` requires the original digest and explicit
`canonical_rows_verified=True` and `unresolved_evidence_preserved=True` attestations.
Those flags cannot override contradictory active migration evidence. Backup cleanup
runs under the verified conversation coordinator and a fenced Redis transaction.
Bare-envelope orphan staging supports bounded `sweep_migration_staging`; interrupted
canonical component migration retains its source and bounded staged evidence and
must be resumed. Unresolved canonical staging is not automatically discarded.

## Combined navigation authority

Fresh canonical navigation generations use the verified Idle absolute session
expiry upfront; `NavigationConfig.session_seconds` is subordinate to that host
session. Existing live legacy navigation with a shorter immutable expiry keeps its
shorter cap. Once that generation expires, it cannot be reopened or extended using
the same Idle session ID; the application must explicitly replace its session or
external authority generation. Millisecond navigation deadlines are rounded down,
so they never extend Idle's absolute authentication deadline.

Canonical navigation stores one operation ledger, with its first accepted activity
result, alongside bounded current projection state. Rendering, business callbacks
and independent stores are not made atomic by this arrangement. The atomic commit
covers the owned navigation projection, activity/deadline, generation and recovery
state. Standalone Idle continues to depend only on its `FlowAdapter` contract.

## Input hardening

Persistent identifiers and JSON parameters must contain valid UTF-8 Unicode scalar
values. Raw surrogate code units are rejected early with a typed error, including a
pair represented as two Python surrogate characters. Actual non-BMP characters,
combining marks and locale text are preserved without normalization or replacement.
