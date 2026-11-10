# Application-owned integration delivery

Approved implementation scope, 10 November 2026. This record separates planned
releases from verified publication. Existing design documents and local changes
are retained.

## Releases

| Package | Published baseline | Target |
| --- | --- | --- |
| aiogram-sentinel | 1.1.0 | 1.2.0 |
| aiogram-cmds | 0.1.1 | 0.2.0 |
| aiogram-coordination | none | 0.1.0 |
| aiogram-nav | 0.1.0 | 0.2.0 |
| aiogram-idle | 0.1.0 | 0.2.0 |

Publish Sentinel and Cmds independently after their complete feature sets pass.
Publish Coordination before Nav and Nav before Idle. Never overwrite published
files or move a release tag. Kit receives documentation only; no Kit release or
PeopleHub application migration is part of this delivery.

## Implementation streams

- **Sentinel:** registered-handler policy propagation, opt-in action-kind buckets,
  explicit exemptions, empty protected-router warning, caller-owned Redis recipe,
  exception passthrough and webhook failure semantics. Existing defaults and
  middleware ownership remain intact.
- **Cmds:** independent rendering locale and Telegram language slot, optional
  language-independent menus, explicit obsolete-slot cleanup, generic profiles,
  rich apply results and caller-owned confirmed fingerprints. Preserve existing
  Boolean wrapper semantics and cancellation propagation.
- **Coordination:** one public task-scoped coordination/fencing contract, memory
  and optional Redis implementations, explicit tracked FSM isolation and public
  custom lease adapters, and read-only external-session contracts. No imports
  from Idle, Nav or Kit. Opaque ownership is rejected rather than assumed.
- **Nav:** shared coordination, external-session binding, application-positioned
  bindings router, intentional root handlers in manual mode, callback rejection
  responder, prepared actions, application-owned rendering/cleanup and draining.
- **Idle:** shared coordination and external sessions, immutable activity
  registration/convenience activation, standalone adapters, coarse observational
  analytics, quiet-hours/DST and shutdown documentation, and combined Nav support.

## Safety and compatibility

The application FSM lock precedes the library storage lock. Borrowed scopes need
actual task ownership; copied context does not authorize a child task. Redis
mutations retain Lua fencing and must not substitute an application lock for
storage ownership. A custom distributed provider must expose a live lease proof.

External session authority never creates, extends or clears application sessions.
The internal generation binds to the external ID and immutable absolute expiry;
the application inactivity expiry is rechecked separately. Lookup failure is not
logout and does not authorize business cleanup. Expired generations retain
unresolved evidence. External databases and Telegram are not transactional with
the library record.

Storage format activation is explicit. Deploy new readers in compatibility mode,
drain old writers, assess/back up storage, then activate/migrate under locks and
CAS. Preserve claims, operations, tokens and unknown effects. No effect callbacks
run during migration. Old binaries cannot share an activated namespace safely.

Redis startup checks remain strict. Managed deployments may explicitly attest
facts unavailable through ACL-restricted introspection, but never override a
contradictory observation. No silent memory fallback or blanket warning mode.

## Verification and publication gates

Each stream supplies regression tests, public API/migration documentation,
runnable examples and its own verification report. Required checks include Ruff,
strict typing/docs, meaningful coverage >=80%, advertised Python endpoints,
minimum/latest aiogram, real Redis 7/8 where relevant, and cross-platform locked
dependency audits. Base artifacts must install without Redis or optional peers.

Review and merge tested candidates before release. Tags, metadata and runtime
versions must agree. Upload exact reviewed wheel/sdist bytes with checksums and
verification evidence. Publication uses the existing tag-bound publisher workflow
identity (and a new one for Coordination). Verify PyPI hashes, clean standalone
installs and published optional-peer resolution after every release.

## Current status

All five target releases are published to PyPI with matching GitHub releases:
Sentinel **1.2.0**, Cmds **0.2.0**, Coordination **0.1.0**, Nav **0.2.0** and
Idle **0.2.0**. Release artifacts match reviewed checksums; clean index-only
standalone profiles passed. Nav and Idle remain independently usable.

Nav PR #1 merged as `f3c5da7`; Idle PR #1 merged as `abd1b81` after final
registry-only CI and independent review. Coordination was published first, then
Nav, then Idle. No temporary peer source overrides remain in release locks or CI.

See [release verification](library-release-verification.md) for workflow links,
artifact evidence and migration boundaries. Existing local Kit design drafts and
mkdocs changes were preserved; no PeopleHub code or deployment was changed.
