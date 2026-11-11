# Redis concurrency and recovery audit

This historical follow-up review checks the standalone Redis implementation against
the reviewed storage, recovery and FSM contracts. It preceded the separately
implemented [optional navigation integration](navigation.md); these Redis fixes
introduced no navigation dependency into the standalone runtime.

## Corrected gaps

| Finding | Correction |
| --- | --- |
| A namespace marker or established configuration could disappear between a Python check and a script | Lua reads and mutations now validate namespace history and the configuration witness atomically; losing established state never bootstraps new defaults |
| Replicas could disagree about retention and storage limits | An immutable namespace profile binds retention, conversation/receipt/token capacities and parameter limits; incompatible clients fail initialization |
| Awaited child tasks could checkpoint effects without the parent Redis lock fence | Effect checkpoints carry the captured coordination scope; backends validate the live, conversation-bound capability and Redis commits compare the actual lock token |
| A revoked handler could acquire a fresh scope and continue | An open revoked scope rejects reentry and unfenced commits |
| Workers omitted the local FSM lock used by incoming handlers | Workers acquire the same verified SimpleEventIsolation instance before Redis; middleware borrows its already-held FSM lock without recursive acquisition |
| Redis FSM keys could alias different bots | Redis FSM key builders must distinguish bot, chat, user and state/data fields; use DefaultKeyBuilder(with_bot_id=True) |
| FSM configuration could change after installation | Middleware checks isolation, normalized identity and actual FSM middleware placement before borrowing |
| Missing jobs and orphan due entries could block queue progress | Bounded polling repairs missing jobs and conditionally removes obsolete due entries; reconciliation parks corrupt records and continues healthy work |
| Corruption could arrive between job validation and claiming | CLAIM compares the exact validated job snapshot before mutation |
| Unknown business effects could lose their ledger through ordinary input | EFFECT_UNKNOWN and QUARANTINED operations block business-handler admission and public activity replacement until explicitly resolved |
| Storage delays could consume the remaining grace budget before sending | Eligibility is checked again immediately before outer/custom and recorded Telegram question stages |
| A foreign ActionReceipt could finish the current operation | Nonempty receipt operation IDs must match the reserved operation |
| An old heartbeat could extend ownership after a newer heartbeat | Ordered renewal timestamps prevent A/B/replay-A from extending the lease again |
| Quarantine could park a repaired replacement snapshot | Classification and CAS now refer to the same captured bytes; unsupported/binary evidence is retained |
| NOSCRIPT retries could misclassify a subsequent script error | Reload is bounded; Redis response-error subclasses consistently halt the affected scope as BackendInconsistent |
| Expired positive evidence could be reported as proof of absence | Expired receipts return unknown_history rather than not_found_within_retention |
| Caught timeouts or lease revocations could leave cancellation bookkeeping behind | Timeout and coordinator scopes remove only their own cancellation request and preserve external cancellation |

## Operational contracts

Configure storage limits identically across replicas. Runtime polling/concurrency
knobs and enablement are not part of the immutable storage profile. Existing
namespaces using an older unversioned layout are rejected rather than silently
rewritten. Migration requires explicit evidence-preserving administrative work;
changing prefixes is not a substitute for resolving old effects.

For Redis FSM storage:

```python
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage

storage = RedisStorage(
    redis=redis_client,
    key_builder=DefaultKeyBuilder(prefix="my-bot:fsm", with_bot_id=True),
)
```

Disabled FSM event isolation remains supported because idle supplies renewable
distributed coordination for the full handler. When SimpleEventIsolation is
enabled, installation binds its exact instance to workers. Configure it before
installation and do not replace it afterward. Custom FSM isolation still requires
a supported adapter and is rejected by the current integration.

`Coordinator.scope_matches(key, scope)` validates a live capability's conversation
binding. Backend implementers must support the optional
`transition(..., coordination_scope=...)` argument used by delegated effect
checkpoints. A captured scope authorizes the guarded checkpoint; it does not
transfer handler lock ownership or make detached tasks safe.

Unknown business outcomes require an operator/application recovery decision based
on external evidence. Under the shared coordinator, trusted recovery code can use
a guarded backend transition to record that decision. Ordinary clear/enter/touch
must not erase the ledger. DELIVERY_UNKNOWN retains its separate documented
supersession behavior. No automatic replay of uncertain business actions was added.

## Verification and boundaries

See [verification results](verification.md) for the current test count, coverage,
compatibility and artifact checks. New real-Redis tests interpose between reads,
validation and commits rather than relying only on timing races. They cover
namespace/configuration loss, profile mismatches, changed claim candidates,
revoked scopes, delegated checkpoints, FSM wait ordering, queue repair, quarantine
and renewal replay. Memory regressions cover the shared recovery contracts.

Redis infrastructure rollback/failover qualification, Redis Cluster, external
session stores and durable analytics remain deferred. Navigation adapters were deferred at this audit and are now implemented separately; see navigation.md.
In-flight Telegram or application requests cannot be retracted by a lease;
application writes still need business-generation checks and idempotency.
