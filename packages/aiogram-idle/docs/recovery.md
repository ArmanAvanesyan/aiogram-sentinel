# Failure and recovery semantics

The memory backend provides conditional state transitions and recovery while its process remains alive. It has no persistence across restart and supports one process only. The optional [Redis backend](redis.md) persists the same evidence and coordinates multiple processes, subject to Redis infrastructure durability. Neither backend can make Telegram effects transactional.

## State and scheduling

Session IDs and activity IDs separate generations. Accepted input advances the activity revision. Deadlines and claims carry those generations; stale heap entries cannot become current merely because a label or conversation is reused.

Mutations deduplicate by stable operation ID and a canonical input fingerprint before checking the original expected version. Retained receipts are bounded. Expired terminal evidence can be pruned, but unresolved recovery evidence is not silently evicted to admit new work.

Claims expire and may be renewed only by their current live owner. A late renewal cannot resurrect ownership. The worker's claim and the conversation coordinator are different resources; both must remain valid before an external stage starts.

## External effects

The runtime records an intent before delivery or a business adapter stage, then records the confirmed result. If a request might have been accepted but its response is lost, the effect is unknown. The default policy suppresses automatic resend. A stale worker cannot advance the current operation after ownership loss.

A known completed abandonment is not repeated when restoration fails. Restoration has its own effects: an unknown restoration send cannot be made safe merely by giving abandonment an idempotency key. Adapters must expose stage receipts or accept an unresolved effect state.

Retry-after is honored without holding a sleeping claim or sending earlier to fit a retry-age budget. Exhausted retries are quarantined with diagnostics rather than silently discarded. Observational event hooks cannot cause a completed Telegram send to repeat.

## Expiry

User inactivity, grace, logical session expiry and physical receipt retention are distinct. The runtime checks that a usable grace period fits before asking and rechecks authorization/resumability on Continue. It does not extend authentication to preserve a draft.

Confirmed grace is anchored to delivery/request timing rather than a late persistence retry. Recovery receipts may outlive the logical session without authorizing resume. Cleanup for an old generation may edit its known inline message, but cannot install an old reply tray over a newer activity.

## What remains application-owned

An activity write is not atomic with an independently stored FSM draft or database transaction. A reliable external producer needs its own transactional outbox or integrated store adapter. Draft mutation must compare the expected business generation as well as deduplicating operation IDs.

The optional Redis backend adds persisted recovery evidence and multi-process fencing; see [Redis setup and recovery](redis.md). Redis data-loss/failover qualification and durable analytics delivery remain outside this implementation.

## API recovery boundaries

ControlResult.accepted means an answer reserved the current prompt, not necessarily that every effect completed. Its outcome reports resuming, delivery_unknown, effect_unknown or quarantined when work is still pending/uncertain. A duplicate completed answer may be stale; it never repeats the completed business action. Backend operation lookup returns OperationLookup: missing entries are unknown_history unless an explicit not_before hint fits the continuous retained-history window. Absence outside that window never proves an external effect did not happen.

Custom presenters must return a receipt matching the reserved conversation, prompt and control tokens, with a finite delivery timestamp. Use the supplied effect recorder for each independent send. Built-in hybrid delivery records its question and tray separately, so a definite tray retry-after cannot duplicate the question. Custom aggregate adapters that cannot expose completed stages are not blindly replayed after uncertainty.

## Review hardening

See [the pre-Redis audit](audit.md) for shared coordination, live effect scopes, tagged operation lookup, explicit aggregate replay opt-in and the corresponding regression cases. Unknown history never authorizes a resend.
