"""Application-owned sessions and optional FSM drafts; no navigation dependency."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import Message
from aiogram_coordination import CoordinationKey, ExternalSession, TrackedEventIsolation

from aiogram_idle import (
    ActionReceipt,
    ActivityRegistration,
    FlowContext,
    FlowEligibility,
    IdleConfig,
    IdleContext,
    IdleConversationKey,
    IdlePolicies,
    IdleRuntime,
    MemoryIdleBackend,
    PromptPolicy,
    QuietHours,
    TelegramPromptPresenter,
    coarse_event_sink,
)
from aiogram_idle.policies import Controls


class DraftState(StatesGroup):
    typing = State()


class ApplicationSessions:
    """Only the application writes these sessions; Idle sees current() alone."""

    def __init__(self) -> None:
        self.sessions: dict[CoordinationKey, ExternalSession] = {}

    async def current(self, key: CoordinationKey) -> ExternalSession | None:
        return self.sessions.get(key)

    def open_by_application(self, key: CoordinationKey, now_ms: int) -> None:
        previous = self.sessions.get(key)
        if previous is None or not previous.is_live(now_ms):
            self.sessions[key] = ExternalSession(
                session_id=secrets.token_urlsafe(18),
                revision="1",
                absolute_expires_at=now_ms + 8 * 60 * 60 * 1000,
                idle_expires_at=now_ms + 30 * 60 * 1000,
            )


@dataclass
class Draft:
    activity_id: str
    text: str = ""


class ApplicationFlow:
    def __init__(self, bot: Bot, dispatcher: Dispatcher, *, fsm: bool) -> None:
        self.bot, self.dispatcher, self.fsm = bot, dispatcher, fsm
        self.drafts: dict[IdleConversationKey, Draft] = {}

    async def inspect(self, context: FlowContext) -> FlowEligibility:
        draft = self.drafts.get(context.key)
        return FlowEligibility(
            resumable=draft is not None and draft.activity_id == context.activity.activity_id
        )

    async def send(self, context: FlowContext, stage: str, text: str) -> None:
        if context.effects is None:
            raise RuntimeError("Application flow requires a stage recorder")

        async def effect() -> dict[str, int]:
            message = await self.bot.send_message(context.key.chat_id, text, parse_mode=None)
            return {"message_id": message.message_id}

        await context.effects.run(stage, effect)

    async def resume(self, context: FlowContext, *, operation_id: str) -> ActionReceipt:
        await self.send(context, "resume-message", "Your draft is still here. Continue typing.")
        return ActionReceipt(operation_id=operation_id)

    async def abandon(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        draft = self.drafts.get(context.key)
        if draft is not None and draft.activity_id == context.activity.activity_id:
            self.drafts.pop(context.key)
            if self.fsm:
                state = self.dispatcher.fsm.get_context(
                    bot=self.bot, chat_id=context.key.chat_id, user_id=context.key.user_id
                )
                if await state.get_state() == DraftState.typing.state:
                    await state.set_state(None)
                    values = await state.get_data()
                    values.pop("draft_text", None)
                    await state.set_data(values)
        return ActionReceipt(operation_id=operation_id, disposition="disarm")

    async def restore(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        await self.send(context, "restore-message", "Draft closed. Use /start to create another.")
        return ActionReceipt(operation_id=operation_id, disposition="disarm")


@dataclass
class Demo:
    dispatcher: Dispatcher
    runtime: IdleRuntime
    sessions: ApplicationSessions
    flow: ApplicationFlow
    application_isolation: SimpleEventIsolation


async def create_demo(
    bot: Bot, *, fsm: bool = False, controls: Controls = "inline", timezone: str = "UTC"
) -> Demo:
    from datetime import time

    application_isolation = SimpleEventIsolation()
    isolation = TrackedEventIsolation(application_isolation)
    dispatcher = Dispatcher(events_isolation=isolation)
    backend = MemoryIdleBackend(config=IdleConfig(enabled=True))
    await backend.activate_storage_format(
        operation_id="demo-format-2", old_workers_drained=True, dry_run=False
    )
    sessions = ApplicationSessions()
    flow = ApplicationFlow(bot, dispatcher, fsm=fsm)

    async def analytics(outcome: str) -> None:
        logging.getLogger("external_sessions.analytics").debug("idle outcome=%s", outcome)

    runtime = IdleRuntime(
        backend=backend,
        session_authority=sessions,
        policies=IdlePolicies(
            {"draft": PromptPolicy(after_seconds=30, grace_seconds=30, controls=controls)}
        ),
        adapters={"application": flow},
        presenter=TelegramPromptPresenter(
            bot=bot, quiet_hours=QuietHours(timezone, time(22), time(8))
        ),
        on_event=coarse_event_sink(
            analytics,
            outcomes={
                "shown": "shown",
                "continued": "continued",
                "cancelled": "cancelled",
                "timed_out": "timed_out",
                "restored": "restored",
            },
        ),
    )
    runtime.install(dispatcher)

    @dispatcher.message(Command("start"))
    async def start(message: Message, state: FSMContext, idle_context: IdleContext) -> None:
        key = idle_context.key
        sessions.open_by_application(
            CoordinationKey(key.namespace, key.bot_id, key.chat_id, key.user_id, key.tenant_id),
            int(backend.clock.now() * 1000),
        )
        previous = await idle_context.current()
        activity = await idle_context.activate(
            ActivityRegistration("draft.typing", policy_id="draft", adapter_key="application"),
            operation_id=f"message:{message.message_id}:draft",
            expected=previous.guard if previous else None,
        )
        flow.drafts[key] = Draft(activity.activity_id)
        if fsm:
            await state.set_state(DraftState.typing)
            await state.update_data(draft_text="")
        await message.answer("Type a draft. After 30 seconds idle, I will ask whether to continue.")

    @dispatcher.message(F.text)
    async def text(message: Message, state: FSMContext, idle_context: IdleContext) -> None:
        draft = flow.drafts.get(idle_context.key)
        activity = await idle_context.current()
        if draft is None or activity is None or activity.activity_id != draft.activity_id:
            await message.answer("Use /start to create a draft.")
            return
        draft.text = message.text or ""
        if fsm:
            await state.update_data(draft_text=draft.text)
        await idle_context.touch(
            expected=activity.guard, operation_id=f"message:{message.message_id}:text"
        )
        await message.answer("Draft saved.")

    return Demo(dispatcher, runtime, sessions, flow, application_isolation)


async def run(*, fsm: bool, controls: Controls, timezone: str) -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("Set BOT_TOKEN before running the example")
    bot = Bot(token)
    demo = await create_demo(bot, fsm=fsm, controls=controls, timezone=timezone)
    try:
        await demo.dispatcher.start_polling(bot, close_bot_session=False)  # pyright: ignore[reportUnknownMemberType]
    finally:
        await demo.runtime.stop()
        await demo.runtime.backend.close()
        await demo.application_isolation.close()
        await bot.session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fsm", action="store_true")
    parser.add_argument(
        "--controls", choices=("reply", "inline", "commands", "hybrid"), default="inline"
    )
    parser.add_argument("--timezone", default="UTC")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("aiogram_idle").setLevel(logging.DEBUG)
    logging.getLogger("external_sessions.analytics").setLevel(logging.DEBUG)
    try:
        asyncio.run(run(fsm=args.fsm, controls=args.controls, timezone=args.timezone))
    except ValueError as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
