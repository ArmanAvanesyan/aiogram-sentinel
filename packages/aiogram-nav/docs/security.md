# Security and deployment boundaries

Report vulnerabilities using [SECURITY.md](https://github.com/ArmanAvanesyan/aiogram-nav/blob/main/SECURITY.md). See the
[security scan policy](https://github.com/ArmanAvanesyan/aiogram-nav/blob/main/reports/README.md) for scan commands, report retention
and severity thresholds. These scans supplement the ownership and recovery
boundaries below; they do not establish application security.

The initial presentation context is an actor-owned private chat. Conversation keys
include bot identity and namespace, and can include tenant scope. Unsupported
chat/topic/business identities require a deliberate adapter; they are never
collapsed onto a guessed private-chat key.

Authorization belongs to application policy. The navigation callback rechecks
permissions for the requested destination/action regardless of whether a visible
button, hidden command, reply label or application handler entered it. Validate
all reconstruction parameters and recheck changing feature availability.

Opaque inline tokens bind to the current actor, conversation, session and view.
Prepared controls are inert until the prepared view commits. Retained stale controls
are acknowledged and stripped best-effort, without changing a newer reply tray.
Reply text and bare commands cannot establish which historical keyboard the user
saw; authorize them against current state.

Do not store bot credentials or full draft text in node metadata, callbacks, log
labels or operation IDs. The examples read `BOT_TOKEN` only at execution time and
report safe node/revision metadata. Libraries do not configure root logging.

Application cancellation writes need stable idempotency keys and business-generation
checks. A task-scoped lock and storage CAS cannot roll back an already accepted
Telegram request or coordinate an unrelated database transaction. Unknown effects
must stay visible until the application resolves them.

Memory storage is for one process and one event loop. It loses evidence on restart.
It is not a replicated session store, durable analytics outbox or full widget/form
framework. No package publication, deployment or infrastructure durability is
implied by these local examples.

When application FSM storage uses aiogram RedisStorage, its known key builder must encode bot/chat/user and state/data fields; configure DefaultKeyBuilder(with_bot_id=True). This validation does not install Redis. The optional standalone Redis repository must be selected explicitly.

Cancellation hooks must authorize their own business-service writes and fence the application draft generation. Destination authorization is not a replacement for business authorization. The memory audit documents setup-time FSM/router invariants and process-local effect-stage ownership.

TextPresenter renderer functions build replayable ScreenSpec plans. Keep planning free of non-idempotent external effects; prepare controls idempotently and perform other external actions through the stage recorder. Never hide a business mutation or Telegram send inside a replayable plan builder.
