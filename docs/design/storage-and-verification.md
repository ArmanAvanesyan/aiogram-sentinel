# Storage failure handling and verification

Status: proposed shared contract for aiogram-nav and aiogram-idle, 10 November 2026.

This specification defines backend parity, conversation isolation, atomic scheduling and failure recovery. It is normative for the [navigation](aiogram-nav.md) and [idle](aiogram-idle.md) plans.

## 1. Identity and concurrency boundaries

Each package owns its public identity type: nav `ConversationKey` and idle `IdleConversationKey`. Neither core imports the other type. Both encode namespace, optional tenant scope, bot_id and normalized context fields compatible with the application's aiogram FSM strategy: chat_id, user_id, thread_id, business_connection_id and destiny where relevant. Serialize unambiguously as a canonical tuple before hashing; do not concatenate unescaped colon-separated user-controlled components.

Within each package, the same normalization drives coordination, storage, callback ownership and background work. The optional nav adapter explicitly maps both identity types and validates a lossless scope match, including lock identity. Sharing field names alone does not imply sharing lock ownership. Defaults must include bot identity even where aiogram's default key builder makes it optional. Namespaces prevent collisions between environments. Persist no bot token in a key.

Private-chat presentation is the initial supported context. If an application uses another strategy, require an explicit adapter and validate its scope; do not substitute chat_id for a missing actor. Telegram inline-mode callbacks without a supported conversation context cannot mutate a private-chat session.

Use exactly one isolation owner:

- Borrow aiogram event isolation only through a configured adapter that verifies a real shared lock implementation, normalized key and ownership scope. DisabledEventIsolation is not a lock. Reject unsafe multi-process configuration, or install a real coordinator covering handlers and workers. A bare FSMContext in handler data does not prove lock ownership.
- Without FSM middleware, install the package's coordinator around relevant updates and worker operations.
- Ownership markers are task-local scoped capabilities, reset in finally; child tasks cannot inherit authority to bypass locks after the parent scope exits. Background tasks acquire independently. No recursive lock acquisition.
- The full protected handler/adapter, not just its final state write, executes under coordination. If FSM and package locks both exist, define one acquisition order and use it everywhere, including workers.
- Conditional versions still protect commits. Lock TTL alone is not a correctness proof.

The current aiogram [StorageKey](https://docs.aiogram.dev/en/latest/_modules/aiogram/fsm/storage/base.html) and [Redis isolation](https://docs.aiogram.dev/en/latest/_modules/aiogram/fsm/storage/redis.html) are integration references. Test exact supported versions because middleware placement and defaults affect ownership.

## 2. Memory and Redis parity

| Property | Memory | Redis |
| --- | --- | --- |
| Each package's activity/navigation state and controls | Same public semantics | Same public semantics |
| CAS and conditional operation IDs | In-process critical section | Atomic Redis scripts |
| Time | Injected wall clock, monotonic waiting | Redis TIME for authoritative commits/claims |
| Deadline queue | Heap plus current-generation map | Sorted set plus versioned job records |
| Claim ownership | In-process tokens and lease records | Redis tokens and lease records |
| Restart | State and jobs lost | Recover retained records subject to Redis durability |
| Multiple processes | Unsupported | Supported against the same authoritative primary |
| Outage fallback | Not applicable | Never silently switch to memory |

Memory expiry is checked on access and periodically swept; cap retained records and token tables. Stale heap entries are harmless only when compared with the current generation, and the heap must be compacted to prevent unbounded activity-driven growth.

Use the same repository contract tests for both backends. Do not emulate Redis wire behavior in the memory backend; implement domain semantics.

## 3. Record ownership and atomic integration

Standalone nav stores a versioned NavigationSnapshot plus bounded action receipts and render recovery metadata.

Standalone idle owns its activity and scheduling record; it has no navigation snapshot. Its record is:

```text
schema_version, store_version, session_id
activity: activity_key, activity_revision, policy_id, adapter_key, params
idle: policy_version, phase, deadline, prompt, retry, pending_operation
components: optional versioned opaque JSON owned by integrations
expires_at, recovery_until
```

Core enter/touch/clear commits activity and due scheduling together. Each entered activity gets a fresh activity_id; activity_key is only a label. Include this ID in jobs, prompt controls, operation guards and component projections to prevent same-key ABA. Every runtime-record mutation increments store_version; accepted activity separately increments activity_revision. Core backend and codec have no dependency on NavigationSnapshot, node IDs or registry semantics.

Only the optional `aiogram_idle.integrations.nav` module implements a `NavigationRepository` projection. It validates and serializes a navigation snapshot into `components["aiogram_nav"]`, maps NavigationMutation into an activity mutation plus component update, and commits both through one backend operation. Idle-only records omit this component. The adapter is the only navigation writer for integrated records; standalone nav can continue using its own repository in applications without this integration.

The idle backend validates an ActivityMutation against current state, resolves its explicit policy, writes activity and any integration-owned component updates, and updates/removes its due index atomically. For combined commits, the nav adapter computes/validates its component and inherited-policy mapping before submitting the mutation with the expected store version. This prevents a crash between session save and deadline scheduling from losing the only wakeup.

Do not implement the atomic guarantee as a post-commit Python callback or separate Redis commands. Use a bounded Lua script or equivalent conditional transaction. Redis [transactions](https://redis.io/docs/latest/develop/using-commands/transactions/) serialize operations but do not make Telegram or another database transactional.

Business FSM data is not part of the generic record. A custom application adapter must expose its own idempotent cancellation/resume and expiry checks. If an existing encrypted session store must remain authoritative, its adapter must support atomic index mutation or a durable schedule-intent outbox with replay. A plain load/save adapter receives no crash-safe scheduling claim. Built-in idle storage guarantees atomic activity/deadline commits independently. An ordinary FSM/database write followed by enter/touch still has a cross-store crash gap; require a durable producer outbox or transactional adapter for stronger delivery. The optional nav projection guarantees its combined commit. Encrypted existing-store adapters are an extension milestone.

Serialization uses a versioned JSON codec, no pickle. Reject unsupported newer schemas and oversized params/history. Optional application codecs can encrypt sensitive record content, while scripts operate on separate minimal scheduling metadata. Claims and due keys still expose opaque identifiers and timing; encryption does not hide activity metadata.

## 4. Redis key layout

Idle prefix: `idle:v1:<namespace>:<tenant>:<bot>`; standalone nav uses its separate `nav:v1:...` namespace. Optional nav component storage uses the idle prefix without adding a core nav dependency; all components are encoded or fixed hashes.

```text
<prefix>:runtime:<conversation_hash>    versioned idle record plus optional integration components
<prefix>:due                           ZSET job_id -> next eligibility time
<prefix>:jobs                          HASH job_id -> metadata
<prefix>:operations:<conversation_hash> bounded operation ledger
<prefix>:controls:<token_hash>          callback/control ownership
<prefix>:outbox                         optional durable event stream
<prefix>:live                           retained runtime membership for reconciliation
<prefix>:expiry                         ZSET runtime_id -> next retention check
<prefix>:config                         versioned policy/enablement manifest
```

`job_id` includes conversation hash, session ID, activity ID and job generation. Job metadata includes phase, expected revisions, deadline, claim token, lease expiry and retry count. Never overwrite a newer job when finishing an older claim.

The due set retains claimed jobs, with score moved to lease expiry. Canonical deadline stays in job metadata. A crashed worker therefore makes the item eligible again without a separate unbounded lease-reaper scan. Renew updates score and lease expiry conditionally only while the existing lease is still live according to Redis TIME. A late renewal cannot resurrect ownership. Each heartbeat has a fresh request ID; replaying one cannot extend the lease again. Terminal finish removes the exact generation only.

Maintain an explicit `:live` index of retained runtime records and an `:expiry` index of logical/physical retention deadlines, updated with runtime mutations. Bounded reconciliation walks this index with a resumable cursor, so a lost due entry can be reconstructed even when no worker can claim it. A missing live index requires explicit administrative SCAN recovery; do not claim arbitrary corruption is self-healing.

Normal atomic transitions remove obsolete generations. Expired sessions discovered by claims are pruned. A bounded periodic sweeper removes abandoned metadata and expired controls. Reconciliation checks record/index consistency and incomplete operations. Avoid whole-keyspace KEYS; use explicit indexes and bounded SCAN only for administrative repair.

Initial backend does not support Redis Cluster: these scripts use multiple keys. Reject Cluster rather than claiming cluster safety with keys that fall into different hash slots. A future sharded design must colocate runtime/jobs/due within each shard hash tag and define cross-shard fairness explicitly.

## 5. Required atomic backend operations

| Operation | Preconditions | Atomic result |
| --- | --- | --- |
| commit_activity | Expected store version/session or absent record, operation ID | Save activity, explicit policy, due job, receipts and optional opaque component updates |
| commit_navigation, optional adapter | Validated nav mutation and lossless identity mapping | Translate to commit_activity with versioned nav component; no second writer |
| claim_due | Eligible score, valid job generation | Assign fresh token, lease expiry, move score; return bounded jobs |
| renew_claim | Matching job generation and token, valid ownership | Extend lease and eligibility score |
| reserve_transition | Current phase/revisions and matching live claim/control | Save operation intent and next phase |
| record_effect | Same operation, stage and expected session | Save confirmed receipt or ambiguity; preserve recovery work |
| finish_or_retry | Exact job/token/operation | Remove, reschedule or replace that job only |
| invalidate_session | Expected session/generation | Remove corresponding jobs/controls and replace or expire runtime |

Scope operation IDs to namespace/conversation/session plus a stable handler/action substep, and retain a fingerprint of canonical mutation inputs. Same ID and same fingerprint returns the existing result; a mismatched payload raises OperationIdConflict. Distinct enter/touch/clear calls in one update need distinct stable substep IDs. Check deduplication before the original expected-version test so a confirmed retry can return its receipt. If the connection drops, query/retry the same ID before issuing another effect. Fingerprint caller intent only; backend-generated timestamps, random activity IDs and retry transport details come from the first persisted result, not a regenerated payload. Deduplication is bounded by advertised retention and surviving Redis data; after that window, delayed producers must revalidate source/session generation rather than assume exactly-once processing.

Lua execution must be bounded. Claim no more than free worker capacity. Never claim a large serial batch and let later items age behind network calls. Use separate per-conversation coordination and a global worker concurrency semaphore.

## 6. Worker algorithm

1. Compute available capacity; claim at most that many jobs using backend time.
2. Start claim renewal promptly; each renewal checks the token and generation.
3. Obtain conversation isolation within a bounded wait, while renewal runs.
4. Reload current runtime, verify session/activity generation, revisions, policy/config digest, logical expiry, phase and canonical deadline. Call side-effect-free flow inspection before a question.
5. Drop obsolete work or atomically reserve the applicable operation.
6. Execute the next adapter/delivery stage with an operation deadline.
7. Persist confirmed stage receipts; finish or reschedule conditionally. Every worker-owned mutation, including record_effect, checks live token/lease and expected operation, not just final acknowledgement.
8. Release isolation and stop renewal. On lease loss, stop starting new effects and relinquish work.

Maintain coordination through the relevant effect/commit sequence. A paused process can outlive a lease and later resume. Conditional fencing protects Redis state, but cannot retract a Telegram request already in flight. Distributed locks do not provide an exactly-once external-effect guarantee. See [Redis locking guidance](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/).

Retry-after is persisted as a future eligibility time rather than a long sleep occupying a claim. Lock contention gets bounded jitter and requeue without being counted as a user-visible send failure. Per-bot delivery limits apply across worker tasks; multiple replicas must also respect shared rate-limit feedback.

## 7. External effects and operation ledger

Example question stages:

```text
intent_reserved -> request_started -> receipt_confirmed -> prompted_committed
                                      or delivery_unknown
```

Example timeout stages:

```text
timeout_reserved -> abandon_confirmed -> outcome_attempted
                 -> restore_confirmed -> committed
```

Persist prompt identity, actor-bound control token and token retention before request_started, so a received inline response can still identify a question whose receipt was lost. Each stage records known Telegram message references. A deleted message is a cleanup result, not proof that abandonment failed. Adapter retries receive the same operation and stage IDs. Treat an ambiguous adapter-internal send as EFFECT_UNKNOWN unless the adapter can query a stage receipt. Never retry an entire restore merely because the preceding abandon was idempotent. If the application cannot make a durable business effect idempotent, expose an unresolved recovery state rather than automatically replaying it.

Unknown sends require a product choice:

| Policy | Behavior | Tradeoff |
| --- | --- | --- |
| Suppress, default | Do not resend an ambiguous question automatically; mark DELIVERY_UNKNOWN | Can miss a question |
| Retry explicitly | Retry with the same logical prompt identity | Can create duplicate Telegram messages |

Neither policy is exactly once. Telegram sendMessage does not provide an application transaction shared with Redis. A durable outbox records intent but cannot resolve the post-send/pre-receipt crash window alone.

For DELIVERY_UNKNOWN, a precommitted actor/session/activity/prompt-bound inline token can prove receipt and authorize an answer after message ownership validation. Reply/command input binds only to the current activity and cannot prove a particular question was seen or justify a shown event. Supersede on explicit accepted activity; never infer delivery from arbitrary text. Otherwise expire recovery metadata after its retention window and let normal session/draft expiry apply. Do not emit a false shown event or automatically destroy a draft under the assumption that the question was seen.

## 8. Failure handling matrix

| Failure point | Required behavior |
| --- | --- |
| Redis unavailable before loading runtime | No protected state transition or idle side effect; return typed unavailability |
| Redis unavailable for optional telemetry | Do not fail successful business handling or repeat delivery |
| Connection lost during commit | Query/retry same operation ID; return CommitUnknown if unresolved |
| Worker dies after claim | Lease eligibility returns job to another worker |
| Worker dies after intent but before send | Recover reserved operation; request_started ambiguity is handled conservatively |
| Worker dies after Telegram acceptance | Delivery unknown unless confirmed receipt is durably available |
| Claim expires while task runs | Old token cannot renew/ack/overwrite; do not begin more effects |
| Fresh activity races with idle | Revision/phase checks select one valid transition; old job cannot cancel the newer state |
| Session expires/recreated | Old session ID invalidates jobs and controls |
| Bot blocked | Mark delivery unreachable, stop delivery retries, delegate business abandonment policy |
| Edit/delete returns missing message | Record cleanup unavailable; continue valid semantic cleanup |
| Retry-after | Requeue at server-provided time plus jitter |
| Authorization or feature access revoked | Invoke authorized application recovery, never render protected draft content; nav target selection is adapter-owned |
| Redis primary failover loses recent writes | Reconcile what remains; document possible lost schedules/receipts and duplicate external effects |
| Shutdown or deployment | Stop claiming, bounded drain, retain/expire recoverable claims, never acknowledge unfinished work |

Redis availability is required for Redis-backed state in either package. An application may keep stateless help/error responses available, but must not execute protected flows against a fabricated empty memory session.

## 9. Expiry and retention

Separate four clocks: user inactivity, prompt grace, business/session expiry and recovery retention. A worker must check all relevant clocks. Record retention may outlive logical session expiry so cleanup can finish, but must not authorize resume after that expiry.

Logical expiry and physical retention are separate fields. Idle clear/disarm must preserve an optional navigation component, operation ledger and needed recovery work. The optional adapter supplies independent nav retention; physical runtime TTL is at least the maximum live component expiry and recovery_until. Idle expiry does not erase an exempt navigation screen. A new session can replace live state only through a guarded operation while old immutable cleanup receipts remain scoped to old generations.

TTL applies to runtime and control keys; shared hash/ZSET entries need explicit bounded pruning. Expiry must not rely on keyspace notifications. Before deleting records, allow retained operation receipts to prove completed work until their recovery window ends.

When idle creation is disabled, remove active pre-prompt schedules or treat them as disarmed, but continue servicing existing prompts and recovery. Re-enabling must explicitly choose whether to arm existing sessions from last activity or only on new activity; default is new activity to avoid a mass prompt burst.

Activity/policy version changes invalidate or migrate pending jobs deliberately. Optional nav integration also migrates registry versions and unknown nodes through an application-configured safe root after authorization checks. Standalone idle requires no root or node migration. Retain old callback token decoding while live prompts require it.

## 10. Test architecture

| Layer | Tools and scenarios | Required evidence |
| --- | --- | --- |
| Pure model | Injected clock, generated registries, state-machine/property tests | Legal transitions and invariants for arbitrary action sequences |
| Repository contract | Standalone nav memory/Redis, standalone idle memory/Redis; optional nav projection separately | Same CAS, expiry, ownership and generation behavior |
| Telegram adapter | Fake Bot session that records method objects and injects responses | Exact markup/message behavior without real network |
| Dispatcher integration | Real aiogram Dispatcher.feed_update, actual middleware/router setup | Input precedence and FSM coexistence |
| Redis integration | Real Redis service with independent clients/processes | Atomic commits, leases, competing polls and restart recovery |
| Fault injection | Kill workers at barriers, block network, delay responses | Stage-by-stage crash behavior and no silent job disappearance |
| Packaging | Separate wheel/sdist, clean standalone and adapter environments | Idle core/Redis run with nav absent; nav runs with idle absent; optional adapter loads only with its extra |
| Manual client UX | Test bot on iOS, Android and Desktop | Sound, banners, unread status, tray replacement and stale controls |

Do not use fakeredis as the sole evidence for Lua, expiry, connection uncertainty or multi-process correctness. Unit tests avoid wall-clock sleeps; integration timeouts have explicit generous upper bounds and deterministic barriers where possible.

### Mandatory race and recovery cases

1. Two workers claim one due job; only the current token commits.
2. More jobs than capacity; unclaimed jobs remain due without premature lease aging.
3. Lease renews during lock contention and a slow send; lost renewal blocks later effects.
4. Old worker acknowledges after a newer activity commit; new schedule survives.
5. Continue and timeout race; one semantic transition wins.
6. Send accepted but response lost; default suppresses blind resend and exposes unknown state.
7. Abandon succeeds then target rendering fails; recovery retries rendering without repeating abandonment.
8. Navigation commit loses its reply after execution; operation lookup avoids duplicate transition/send.
9. Session expires and is recreated with same chat/user; old controls remain inert.
10. Tenant/bot/topic identity collisions are rejected or isolated according to declared support.
11. Redis outage and reconnect; no process-local fork of the session appears.
12. Record/index corruption repair; bounded reconcile restores or quarantines work and emits an alert.

### Interaction and backend matrix

Run three separately gated matrices, each with reply-only, inline-only, command-only and hybrid against memory and Redis. Standalone nav covers entry, parameters, Back, Cancel and locale changes with idle absent. Standalone idle covers enter/touch/clear, draft input, prompt, Continue, grace timeout, exemption and restoration with nav absent. The optional combined matrix adds inherited node policies, atomic nav/activity mutations, navigation reconstruction and shared control routing. Assert Telegram API call shapes as well as stored state.

For hybrids, verify one message never receives both inline and reply markup, reply removal is explicit, and inline-only refresh does not inadvertently replace the tray. For commands/reply, test delayed controls against current state and document their lack of prompt-specific provenance.

## 11. Observability and release gates

Metrics: due backlog and oldest due age, claim/renew failures, lock wait, version conflicts, processing latency, retry-after count, unknown delivery count, restore failures, expired jobs, reconcile repairs and shutdown drain outcome. Labels use bounded policy/stage names rather than user IDs or arbitrary node params.

Logs include safe conversation hash, session generation, operation ID, stage and revisions. Debug logging is enabled in development examples and controllable by the application. Libraries do not globally configure the root logger.

Release gates:

- All public APIs have behavior and typing tests; security-sensitive ownership/authorization cases are complete.
- At least 80% line coverage, plus meaningful transition and failure branch coverage.
- All eight style/backend combinations pass for each standalone package with the other absent. A separate eight-case combined matrix gates only the optional integration.
- Dependency metadata, import graph and clean-install checks prove idle core/Redis need no nav and nav needs no idle.
- A seeded 1,000-job killed-worker run has no unexplained missing jobs; every job is terminal, scheduled, leased or explicitly quarantined/unknown.
- No duplicate semantic abandonment with idempotent test adapters. Duplicate Telegram effects in configured ambiguous-send cases are classified, not hidden by an invalid zero-duplicates assertion.
- Supported Python/aiogram/Redis matrix passes in CI; unsupported versions fail with actionable messages.
- Bounded-load tests show no unbounded heap, token, ledger or task growth. Publish measured conditions rather than unsupported throughput promises.
- Built artifacts install without a source checkout; memory extras run with Redis absent.
- Neutral demonstration apps and manual client results support readiness claims. A specific consuming project, ticket, business flow, analytics service or deployment order is not a standalone library release dependency.


## 12. Redis execution and recovery requirements

Scripts validate types, schema, payload bounds, versions and ownership before the first write. Atomic execution means no interleaving; it is not rollback after a runtime error. Do not wrap a sequence in MULTI/EXEC and assume command errors undo earlier writes. A script/runtime error after possible writes is BackendInconsistent: halt effects for affected scope and reconcile/quarantine before resuming. See [Redis transaction error semantics](https://redis.io/docs/latest/develop/using-commands/transactions/).

Use packaged, versioned scripts with EVALSHA and bounded NOSCRIPT reload/retry. Reloading script code does not change operation identity. Treat connection loss as unknown execution, not NOSCRIPT. Claims with an unknown result may be left to expire; replay must not claim an additional batch beyond reserved capacity. Redis script caches are volatile across restart/failover; see [script cache recovery](https://redis.io/docs/latest/develop/programmability/eval-intro/).

Require noeviction for the reliable backend profile, bounded client timeouts, permitted script commands and an authoritative writable primary. Refuse or explicitly mark degraded durability if these cannot be verified. Do not assume Redis-managed Sentinel and aiogram-sentinel are the same component. Redis persistence/replication loss remains outside package guarantees. Check Redis wall-clock drift; clock jumps can accelerate/delay leases and deadlines, and must be observable.

Renewal failure, including an unknown renewal result, stops starting further external stages until ownership is confirmed. It does not erase a request already in flight. reserve_transition, record_effect and finish_or_retry all enforce token, live lease, session/activity and operation generation. A replacement claimant recovers the persisted stage; it does not resend a stage already marked request_started. Late receipts may be attached as immutable diagnostics by a separate guarded recovery path, but a former owner cannot advance the current lifecycle.

Every nonterminal operation must have a recovery job in the due index, even when its ordinary activity deadline has been removed. Controls use a newly reserved operation/recovery job, not the old idle job's dead token. Retry exhaustion persists QUARANTINED plus reason and last stage until its retention deadline. Lock contention does not consume send-attempt count, but a total age limit prevents endless spinning. Retry-after is never shortened to fit an age budget; quarantine instead. Reconciliation only rearms work whose canonical record proves a missing schedule; it never invents a fresh question or business cancellation from an unknown effect.

Cancellation and shutdown use the same rules as crashes: checkpoint confirmed receipts when possible, preserve unknown requests, release no unfinished stage as successful, and let a still-live claim expire. A memory process restart cannot retain any such evidence and has deliberately weaker recovery guarantees.

## 13. Optional navigation integration transaction rules

The integration requires a backend capability for guarded opaque component reads/updates in the same atomic activity/index commit. Third-party backends lacking it reject integration setup rather than falling back to post-commit hooks. Core validates generic JSON/size limits; only the adapter interprets its component schema. Unrelated components and retained old-operation receipts are preserved.

Mapping rules are explicit:

| Navigation event | Idle mutation |
| --- | --- |
| User enters a different activity, or explicitly restarts one | Fresh activity_id and one accepted-activity increment |
| User refresh/tab/parameter action within the same declared activity | Preserve activity_id; advance activity_revision once |
| Background render or cleanup | Update view/component only; do not touch last_activity_at or extend a user deadline |
| Enter an exempt node | Disarm ordinary idle scheduling while preserving nav snapshot and recovery receipts |
| Continue/restore during an idle operation | Stage navigation intent under that operation, then atomically complete component and lifecycle |

Node-to-activity grouping is adapter configuration, default one node per activity; no prefix guessing. The adapter's displayed nav activity revision and idle activity revision share one mapped acceptance counter. Standalone enter/touch/clear writes to an integrated slot are rejected; application text uses integration.touch with mapped guards. Identity/lock mapping, not Redis key prefix alone, establishes shared coordination.

Navigation prepare reserves an operation without changing the committed node or accepted-activity clock. While a render is unresolved, idle processing routes to operation recovery instead of asking about the old screen. The coordinator covers preparation/effects/completion; operation fencing still applies after lease loss. A crash after render does not authorize completion until confirmed receipts and current ownership match. Unknown sends are surfaced and not rerendered blindly.

Ordinary idle clear/expiry never deletes navigation content. Navigation and idle session generations must map explicitly, not be regenerated independently by two factories. Registry migration or writer-format changes require an explicit versioned migration while workers are stopped/draining; a flag flip is not a storage migration.

## 14. Policy and configuration changes across replicas

Persist each active policy's immutable resolved snapshot/digest with the activity and prompt. Store a namespace-level enablement/policy manifest generation. Workers may process only supported schema, operation and policy versions; unknown/newer versions are parked with diagnostics instead of recomputed using local defaults. All replicas check manifest generation when accepting mutations/reserving effects. A rolling-deploy mismatch cannot let one worker re-enable work disabled by another.

Creation disablement applies to both prompt and quiet restore. Already-reserved operations drain under their recorded semantics; changing a boolean cannot retract an in-flight Telegram request. Existing grace deadlines are not reset by a deployment, language change or receipt retry. Removing an adapter or policy referenced by live work is blocked until migration, drain or explicit quarantine. Re-enablement defaults to new accepted activity, with no bulk rearm.

If runtime creation is disabled or policy is exempt, still retain the activity/component state needed for the consumer's semantics, without creating ordinary due jobs. Optional cleanups/recovery retain their own jobs. Pin the immutable policy snapshot in retries and require explicit migrations for changed meanings of the same policy ID.

## 15. Additional pre-implementation acceptance cases

- Default disabled FSM isolation is detected; background and incoming handlers cannot mutate business state concurrently.
- Child tasks cannot reuse a stale coordination marker; task cancellation resets scoped ownership.
- Same session/key re-entry gets a fresh activity generation; stale guard cannot touch/clear it.
- Deduplicated retries return original receipts before checking stale CAS; payload mismatch is an explicit error.
- NOSCRIPT, lost claim replies, runtime errors, eviction and expired late renewals follow distinct recovery paths.
- A runtime missing its due entry is found via live-index reconciliation; a missing live index requires administrative recovery.
- Prompt tokens exist before send; delayed confirmed receipts do not grant a new grace window.
- Unknown restore/custom adapter effects cannot trigger blind whole-adapter replay.
- Idle clear/expiry preserves exempt navigation, unrelated components and retained operation receipts.
- A prepared nav render blocks old-screen prompting and can complete without duplicate rendering after idle-only CAS changes.
- Mixed policy/config generations across replicas cannot create work under incompatible semantics.
- Short session lifetime and long recovery retention coexist without extending authentication or shortening promised grace.


## 16. Coordination and external-state limits

Job lease and conversation lock are different resources. Renewing one does not renew the other. A distributed coordinator must renew/verify its conversation lock or enforce an operation deadline shorter than the verified lock lifetime with safety margin; a Redis job lease alone is insufficient. Borrowing aiogram isolation is allowed only when its lock lifetime and ownership semantics meet that contract. Default or unknown lock settings fail startup validation for reliable multi-worker use. Long handlers must opt into a compatible renewable coordinator or bounded execution.

No finite lock eliminates paused-process external effects. Application draft mutations must compare the owned session/activity or durable draft version as part of the business write, as well as deduplicating operation/stage IDs. An adapter that cannot fence business state must declare this limit; the library cannot guarantee an expired old process will never modify that database. This qualification applies to standalone FSM integrations and the optional nav integration equally.

Safe cleanup is generation-specific: editing/removing buttons on an old known inline message can be allowed after supersession, but sending an old reply tray/removal or touching business state requires the still-current generation. Expired-session recovery must not overwrite a newer user's keyboard. Opaque token acknowledgement is observational; consuming a token reserves a conditional operation and supports deduplicated retries rather than deleting the only recovery evidence.

A lost receipt cannot be classified as a definite unsent stage merely because its ledger entry is absent after Redis data loss. During ordinary retained-state recovery, request_started means unknown unless a durable receipt proves otherwise. After detected storage rollback/failover loss, report degraded guarantees and require explicit recovery policy; no script can reconstruct effects from missing history.


## 17. Backend protocol and result contract

IdleBackend is an idle-owned protocol, implemented by memory and Redis. It supplies load, open/replace session, commit_activity, lookup_operation, claim_due, renew_claim, reserve_transition, record_effect, finish_or_retry, reconcile_page and apply_config. Every conditional write returns a tagged result: committed, duplicate, conflict, expired, ownership_lost, unsupported_version or quarantined; connection uncertainty raises CommitUnknown. Public contexts translate these into documented errors without retrying external effects.

A successful commit returns store_version, activity snapshot/guard, deadline generation and operation receipt. ActivityMutation carries operation ID, canonical-input fingerprint, expected guard/version, change kind, accepted-activity flag and optional capability-authorized component updates. Core backend operations never accept a navigation class. The optional adapter uses versioned opaque JSON and the generic operation protocol; unsupported third-party capabilities fail setup.

Querying a missing operation returns not_found_within_retention only when retained generation/tombstone evidence supports it. After retention loss or storage rollback, return unknown_history, not proof that an effect did not happen. Bounded receipt pruning must preserve pending/recoverable operations; capacity exhaustion rejects new work with an explicit overload error rather than evicting unresolved evidence.

ConfigManifest contains generation, enablement, policy digests and supported record/operation versions. Initial creation is CAS-on-absent; configuration updates require an explicit trusted apply_config with expected_generation. A worker cannot overwrite the manifest on startup. Duplicate administrative request IDs return the prior manifest result. A configuration mismatch fails write admission or parks incompatible jobs, with a health signal and an explicit migration path.


## 18. Memory implementation audit clarifications

The pre-Redis memory audit tightened the backend contract: shared coordinator binding with live scope capabilities; namespace/bot-filtered claims; immutable payload fingerprints; and tagged operation lookup with an explicit retained-history hint. The local Redis implementation now satisfies these contracts with authoritative persistence and distributed coordination, real-server concurrency/crash tests and separate memory/Redis parity tests. The memory tests alone do not establish Redis guarantees; infrastructure failover/data-loss qualification remains separate.

Confirmed effect results survive later state-commit failures. Typed effect receipts use a tagged envelope distinct from application JSON. Aggregate adapter reentry requires explicit replay_safe opt-in and stage-recorded/idempotent subeffects; unknown individual sends remain conservative by default. Pending work cannot be erased by reentrant public activity APIs or retention pruning. Dispatcher admission blocks ordinary business handlers during reserved recovery, while normal accepted input can supersede a PROMPTED question.

A recorded question receipt is recovered before new-send eligibility checks, preserving its original grace deadline. Answer admission checks that deadline even when polling is delayed. See the local implementation's `docs/audit.md` and `docs/verification.md` for fixes and test evidence.


## 19. Redis review implementation clarifications

The local Redis review enforces namespace history and the established-configuration
witness inside atomic scripts. An immutable storage profile binds retention and
capacity limits across replicas; changing runtime polling knobs does not change
that profile. Claims compare validated job bytes, and ordered heartbeat retries
cannot extend a later lease.

The coordinator contract includes scope_matches(key, token). Delegated effect
checkpoints pass coordination_scope to transition; this validates a live,
conversation-bound capability without transferring handler ownership. Workers
share the verified SimpleEventIsolation instance and acquire it before Redis.
Known Redis FSM key builders must encode bot/chat/user/field identity. Retained
unknown/quarantined business operations block ordinary activity until resolved.

See the sibling library's docs/redis-audit.md and docs/verification.md for tested
fixes and limitations. These changes do not implement navigation integration.


## 20. Standalone navigation Redis implementation

The local aiogram-nav Redis backend now implements the audited standalone
repository protocol without importing aiogram-idle. It uses authoritative
per-conversation JSON CAS, server-time expiry checks, renewable fenced
conversation locks, immutable storage profiles and retained operation/token
receipts. Confirmed partial rendering survives process death; uncertain sends
remain blocked from automatic replay. A permanent live-index witness prevents
silent capacity reset after index loss, and strict envelope invariants reject
hidden or contradictory pending work.

The sibling package's docs/verification.md records real-server concurrency,
process-crash, partial-Lua-error, callback-ownership, FSM and memory-parity tests.
Its docs/redis.md describes bounded sweeping and fail-closed corruption handling.
Administrative index rebuilding, infrastructure rollback detection, Cluster and
the optional combined idle/navigation adapter are not implemented by this slice.


## 21. Standalone navigation Redis audit clarifications

The follow-up local audit requires revoked conversation scopes to remain counted
until protected handler cleanup finishes. Borrowing supports the exact verified
SimpleEventIsolation implementation; unsafe custom subclasses are rejected.
Real Redis FSM storage with independent clients verifies full-handler ordering
and fresh state-filter dispatch under the distributed lock.

Rejected callbacks acknowledge only: a stale token does not prove ownership of
its message, and a prepared view can already have been delivered. Post-commit
cleanup verifies current generation after observational hooks and supplies a
per-effect ownership guard to presenters. Sweep operations validate namespace
history atomically and serialize their shared scan cursor. Persisted receipts
validate immutable expiry and conversation-bound render references; invalid
caller checkpoints are rejected before storage in either backend.

See aiogram-nav/docs/redis-audit.md and docs/verification.md for regression
coverage. These corrections do not implement the optional idle adapter.


## 22. Optional navigation projection implementation

The optional aiogram_idle.integrations.nav module now projects the reviewed
navigation repository onto an idle-owned `aiogram_nav` component. Generic
component transactions atomically update the component, activity and due index
without either core importing the other package. The adapter validates matching
identity/session mapping, policy inheritance, explicit activity groups and one
mapped acceptance counter. Integrated slots reject standalone activity writers.

Staged idle rendering carries generic ActionReceipt.component_updates. The owning
idle operation’s final transition applies these updates and lifecycle changes
together. Component preparation/checkpoint writes preserve the exact captured
worker claim; they never infer a successor token. Pending navigation has its own
recovery scheduling and suppresses old-screen prompts/answers. Uncertain or
unauthorized recovery parks retained evidence instead of resending.

One combined middleware owns installation, verified FSM borrowing and control
precedence. Install neither standalone middleware first. Tracked post-commit
cleanup is observational and guarded before each external effect. Generic
components/effect receipts are bounded at 8 MiB and full storage envelopes at 32 MiB;
pooled operation receipt capacity also bounds staged writes. Kit dependency extras
and publication remain separate milestones. See aiogram-idle/docs/navigation.md
and docs/verification.md for executable APIs, local tests and deployment limits.
