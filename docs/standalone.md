# Standalone integration

`aiogram-idle` needs accepted activity and application callbacks. It does not need a screen tree, a root menu or aiogram-nav. It can run beside ordinary handlers or an aiogram FSM; it never owns the business draft.

## Policies and adapters

`IdlePolicies` maps explicit policy IDs to `ExemptPolicy`, `PromptPolicy` and `QuietRestorePolicy` values. A `PromptPolicy` declares its idle delay, grace period and controls (`reply`, `inline`, `commands` or `hybrid`). Parent inheritance is not a core feature.

A flow adapter implements four asynchronous operations:

- `inspect(context)` checks current authorization, resumability and known draft expiry without effects.
- `resume(context, operation_id=...)` reconstructs the application's activity without discarding its draft.
- `abandon(context, reason=..., operation_id=...)` clears only the owned business state.
- `restore(context, reason=..., operation_id=...)` presents the application-defined post-cancellation UI.

Adapters return `ActionReceipt` values to checkpoint their effects and choose rearm/disarm behavior. Use stable operation/stage IDs and compare the application's own draft generation when performing durable writes. Business idempotency does not make a Telegram send transactional.

## Session and activity ownership

Use `idle_context.open_session()` to allocate an idle-owned session, then `enter()` its first activity. `current()` returns an immutable snapshot with its guard. Later accepted draft input calls `touch(expected=snapshot.guard, operation_id=...)` without changing the business step. `clear()` invalidates idle state while leaving draft cleanup to the application.

Use distinct stable operation IDs for logical substeps, for example `update:123:open`, `update:123:enter` and `update:124:accept-text`. Retrying the same substep returns its receipt; reusing an ID with a different payload is a conflict. Absolute session expiry is not extended by activity.

Entering a replacement activity requires the current guard. Every entry receives a fresh activity generation, even if its label is unchanged. A stale control or worker cannot overwrite that generation. Reply/command controls still cannot prove which historical prompt the person saw.

## Dispatcher integration

Call `idle.install(dispatcher)` before polling or feeding updates. The package injects `idle_context` and coordinates the complete protected handler, not just its final touch call. It does not consider every incoming message to be accepted activity: rejected input and failed handlers leave the prompt/grace state intact unless the application explicitly commits acceptance.

When the dispatcher has real FSM event isolation, workers and updates must use the same verified lock identity. Disabled isolation is not a lock. Do not share memory-backed runtime state across processes or install duplicate competing coordinators. The package must not recursively acquire a lock already borrowed by the current task.

The application owns feature flags, locale selection, draft persistence and authorization. Register application command handlers without duplicating the idle router's active-prompt controls. `/cancel` without a live prompt can fall through to the application's ordinary cancellation flow.

## Presentation and localization

`TelegramPromptPresenter` accepts a Bot, `PromptTexts` or a locale-to-text resolver, and an optional quiet-hours resolver. The question is a new message. A confirmed outcome can edit it. Restoring or removing a reply keyboard needs a message carrying the replacement markup; an inline edit alone does not change the reply tray.

For hybrid UI, inline controls and reply trays may require separate messages. Configure each explicitly instead of putting both markup kinds on one send. The application restoration adapter owns the final tray.

Quiet hours must use an application-selected IANA timezone. The host clock timezone is not a tenant preference. A silent message has no sound but may still display a notification.

## Supersession and configuration

After successful enter/touch supersedes a prompt, the library strips old inline controls best-effort. It does not install or remove a reply keyboard over UI the application just rendered. An ordinary text handler accepting input while a reply prompt is open must send its intended replacement tray or ReplyKeyboardRemove; the demo does this. Continue/cancellation adapters likewise own the final tray. Cleanup failure does not roll back accepted business input or repeat its effects.

Use `IdleRuntime(locale_resolver=...)` to resolve and freeze the prompt locale before delivery; the built-in presenter also accepts an optional async locale resolver for applications using it independently. The persisted receipt locale selects answer labels even if the application language subsequently changes. Activity acceptance is explicit, not automatic middleware behavior.

Configure storage capacities on MemoryIdleBackend(config=...). Scheduling and worker limits use IdleRuntime(config=...); supplying the same IdleConfig instance to both is the simplest setup when customizing limits. Call initialize() and read the backend manifest before using apply_config(expected_generation=..., update=ConfigUpdate(...)). Configuration updates are trusted application/admin actions, never bot commands installed by this package.

## Running examples

The shared [demo](https://github.com/ArmanAvanesyan/aiogram-idle/blob/main/examples/demo.py) has `--controls` and `--fsm` switches. It keeps sample drafts in process, just like the package's memory backend. It demonstrates the four control styles; it is not a durable draft-store implementation.

Use `/draft`, type sample text, wait for the prompt and exercise Continue, Cancel and grace expiry. `/status` shows safe lifecycle metadata. Set a short delay only for development. Tokens are supplied through `BOT_TOKEN`; never commit them.

## Backend and navigation extension points

The backend, coordinator, clock, session-authority, effect-recorder and presenter contracts are idle-owned. The memory implementation exposes capability reporting and opaque component storage, but neither interprets navigation types.

[Redis storage](redis.md) is available through the optional `redis` extra, independently of navigation. The optional [navigation integration](navigation.md) is available through `nav`; neither base nor Redis-only installations require it. Consumers should not infer distributed durability from the memory backend's claim/lease API.

## Sharing a memory backend

Runtimes attached to one backend use its shared coordinator. Configure FSM isolation before creating activity; incompatible or active coordinator replacement is rejected. Runtimes sharing a namespace must serve the same policy/adapter meanings. Workers claim only their own namespace and, when a Bot is bound, that bot. The built-in presenter binds its known Bot even without dispatcher installation.

Adapters must await delegated effects and must not call public enter/touch/clear while their own reserved operation is running. Return staged replacement intent instead. See [the audit](audit.md) before opting an aggregate adapter into replay.

While `is_busy(key)` is true, dispatcher integration handles idle controls and returns a busy response instead of admitting ordinary business handlers. Retained unknown/quarantined business effects are busy too; ordinary acceptance cannot discard their ledger. This protects reserved resume/abandon/restore work during retries. Direct integrations must make the same admission check under shared coordination before changing application state. An open PROMPTED question is not a reserved operation: accepted ordinary input can still supersede it normally.

Redis FSM key builders must include bot identity (for example `DefaultKeyBuilder(with_bot_id=True)`). See the [Redis audit](redis-audit.md) for verified FSM lock ordering, immutable storage profiles and backend scope contracts.
