# Concurrency and recovery audit before Redis

This historical review records the standalone memory implementation before Redis
and optional navigation integration were added. Its results describe that phase,
not the current feature inventory. See [current architecture](architecture.md) and
[verification](verification.md) for subsequent work. No publication or deployment
was included in this review.

## Findings fixed

| Gap | Corrected behavior |
| --- | --- |
| Runtimes sharing storage had independent locks | The backend owns shared coordination; unsafe rebinding after activity or during active/waiting scopes is rejected |
| FSM borrowing could claim a lock the dispatcher did not hold | Borrow only the exact installed isolation instance; reuse compatible isolation and reject conflicts |
| Copied contexts could restore expired ownership | Live scope nonces are required, including when the original task restores an old context |
| Delayed Continue could outlive grace | Answer reservation checks the canonical grace deadline, independently of poll timing |
| Saved delivery recovery repeated fresh-send lifetime checks | Confirmed receipt recovery restores the original grace before new-send inspection |
| Captured effect recorders outlived their operation scope | Recorders bind to live coordination and session/activity generations |
| Concurrent equal effect stages could send twice | Per-stage serialization replays one confirmed result; checkpoint writes are serialized across distinct stages |
| Typed receipt replay lost values | Tagged ActionReceipt, DeliveryReceipt and PromptReceipt results round-trip without colliding with ordinary JSON |
| Stage names could overwrite receipt metadata | Empty, oversized, recursive and reserved result-prefix stage names are rejected |
| A retry after a later commit failure could erase a confirmed stage | Confirmed receipts survive retry scheduling, so completed restoration is not repeated |
| Interrupted aggregate adapters could not consult nested receipts | Explicit replay-safe aggregate adapters can reenter; unconfirmed individual effects still stop automatic replay |
| Forbidden delivery was retried under ambiguity opt-in | Permanent forbidden delivery is quarantined before ambiguous retry policy is considered |
| Public activity calls could erase their own reserved effects | Reserved operations reject enter/touch/clear/session replacement; replacements are staged in ActionReceipt |
| Mutable inputs could change a fingerprint after detachment | Fingerprints use the same frozen payload that is committed |
| Administrative receipts never freed capacity | Configuration receipts use bounded expiring retention |
| Pending evidence could be silently pruned | Unfinished operations and live claims are protected until explicit completion/quarantine |
| Shared-backend workers could claim foreign jobs | Claims filter the runtime namespace and bound bot while preserving foreign heap entries |
| Missing operation receipts looked like proof of no effect | Tagged lookup distinguishes found, provable absence and unknown history, including clock rollback |
| A worker error could leave other batch tasks unobserved | Batches await every task and report pending/unknown work as failed processing; managed polling survives transient backend failures |
| An adapter could leave fire-and-forget effects behind | Completion rejects outstanding started stages instead of deleting their evidence |
| Ordinary input could mutate business state while recovery still owned it | Dispatcher handlers are gated while an operation is reserved; is_busy supports custom integrations |
| Presenter and dispatcher could disagree about bot identity | Constructor/startup validate identities before binding; known presenter bots also constrain standalone worker routing |

## Adapter recovery contract

Use unique stage names for each external action. Await every delegated effect before returning an ActionReceipt. The recorder is valid only inside its originating live conversation scope; do not retain it for later handlers or activities.

The default remains conservative: an interrupted aggregate adapter is not blindly invoked again. An adapter may explicitly declare `replay_safe = True` only when all external actions use the supplied recorder and all other business writes are idempotent for their operation/stage IDs. Such an adapter can be called again to replay confirmed nested receipts. An individual unconfirmed send still becomes unknown unless that individual action is explicitly declared safe to repeat.

The built-in Telegram presenter uses recorded per-message stages and supports safe aggregate reentry. This does not turn Telegram delivery into an exactly-once operation. Default ambiguity handling still suppresses replay of unconfirmed individual sends.

## Lookup and coordination contract changes

`lookup_operation` now returns OperationLookup. A missing result defaults to unknown_history. A caller supplying not_before can establish absence only within the backend's continuous retained-history window; receipt expiry, process restart or a backwards clock movement must not manufacture proof that an effect never happened.

Backend implementations provide shared coordinator binding, live scope capabilities and namespace/bot-filtered claims. These contracts must be implemented by Redis explicitly; the memory implementation is not evidence of distributed lock or persistence behavior.

## Verification

See [verification results](verification.md) for the final test count, coverage, compatibility and package checks. The audit adds deterministic race/failure regressions and a 1,000-activity abandoned-claim accounting test. This report describes the original memory audit. The subsequent Redis implementation and process-crash verification are recorded in [Redis setup](redis.md) and [verification results](verification.md). Real Telegram-client UX and infrastructure failover/data-loss qualification remain unverified.
