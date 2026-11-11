"""Run a private-chat idle demo; BOT_TOKEN is read only when main executes."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Literal, cast

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from aiogram_idle import IdleConfig, IdleContext, IdlePolicies, IdleRuntime, PromptPolicy
from aiogram_idle.models import (
    ActionReceipt,
    FlowContext,
    FlowEligibility,
    IdleConversationKey,
)
from aiogram_idle.presentation import TelegramPromptPresenter
from aiogram_idle.storage.memory import MemoryIdleBackend

Controls = Literal["reply", "inline", "commands", "hybrid"]


class DraftFlow(StatesGroup):
    typing = State()


@dataclass
class Draft:
    text: str = ""
    activity_id: str = ""


class DemoAdapter:
    """Application-owned state, independent of navigation and idle storage."""

    def __init__(self, bot: Bot, dispatcher: Dispatcher, *, fsm: bool) -> None:
        self.bot = bot
        self.dispatcher = dispatcher
        self.fsm = fsm
        self.drafts: dict[IdleConversationKey, Draft] = {}

    async def inspect(self, context: FlowContext) -> FlowEligibility:
        draft = self.drafts.get(context.key)
        return FlowEligibility(
            resumable=draft is not None and draft.activity_id == context.activity.activity_id,
            expires_at=context.activity.expires_at,
        )

    async def _send(self, context: FlowContext, *, stage: str, text: str) -> None:
        async def send() -> dict[str, int]:
            message = await self.bot.send_message(
                context.key.chat_id,
                text,
                reply_markup=ReplyKeyboardRemove(),
                parse_mode=None,
            )
            return {"message_id": message.message_id}

        if context.effects is None:
            raise RuntimeError("The demo requires the runtime effect recorder")
        await context.effects.run(stage, send)

    async def resume(self, context: FlowContext, *, operation_id: str) -> ActionReceipt:
        draft = self.drafts.get(context.key)
        if draft is None or draft.activity_id != context.activity.activity_id:
            return ActionReceipt(operation_id=operation_id, disposition="disarm")
        await self._send(
            context,
            stage="demo-resume",
            text=f"Continue typing. Your draft is preserved ({len(draft.text)} characters).",
        )
        return ActionReceipt(operation_id=operation_id)

    async def abandon(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        draft = self.drafts.get(context.key)
        if draft is not None and draft.activity_id == context.activity.activity_id:
            self.drafts.pop(context.key, None)
        if self.fsm:
            state = self.dispatcher.fsm.get_context(
                bot=self.bot, chat_id=context.key.chat_id, user_id=context.key.user_id
            )
            await state.clear()
        return ActionReceipt(operation_id=operation_id, disposition="disarm")

    async def restore(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        await self._send(context, stage="demo-restore", text="Use /draft to start again.")
        return ActionReceipt(operation_id=operation_id, disposition="disarm")


def build_demo(bot: Bot, args: argparse.Namespace) -> tuple[Dispatcher, IdleRuntime]:
    """Construct without polling or making network calls; useful for smoke tests."""
    dispatcher = Dispatcher()
    adapter = DemoAdapter(bot, dispatcher, fsm=args.fsm)
    runtime = IdleRuntime(
        backend=MemoryIdleBackend(),
        policies=IdlePolicies(
            {
                "draft": PromptPolicy(
                    after_seconds=args.after,
                    grace_seconds=args.grace,
                    controls=cast(Controls, args.controls),
                )
            }
        ),
        adapters={"demo": adapter},
        presenter=TelegramPromptPresenter(bot),
        config=IdleConfig(enabled=True, poll_seconds=1),
        namespace="idle-demo",
    )
    runtime.install(dispatcher)

    def key_for(message: Message) -> IdleConversationKey:
        if message.from_user is None:
            raise ValueError("This demo supports actor-owned private chats")
        return IdleConversationKey(
            namespace="idle-demo",
            bot_id=bot.id,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
        )

    @dispatcher.message(Command("draft"))
    async def start_draft(message: Message, idle_context: IdleContext, state: FSMContext) -> None:
        key = key_for(message)
        existing = await runtime.inspect(key)
        prefix = f"message:{message.message_id}"
        if existing is not None and existing.session.expires_at > runtime.backend.clock.now():
            session = await idle_context.replace_session(
                expected=existing.session.guard,
                operation_id=f"{prefix}:replace",
                lifetime_seconds=1800,
            )
        else:
            session = await idle_context.open_session(
                operation_id=f"{prefix}:open", lifetime_seconds=1800
            )
        activity = await idle_context.enter(
            "draft.typing",
            policy_id="draft",
            adapter_key="demo",
            params={},
            session_id=session.session_id,
            expires_at=session.expires_at,
            operation_id=f"{prefix}:enter",
        )
        adapter.drafts[key] = Draft(activity_id=activity.activity_id)
        if args.fsm:
            await state.set_state(DraftFlow.typing)
        markup = (
            ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Draft help")]], resize_keyboard=True
            )
            if args.controls == "hybrid"
            else ReplyKeyboardRemove()
        )
        await message.answer(
            "Type a draft, then wait for the idle question. /status shows lifecycle metadata.",
            reply_markup=markup,
        )

    @dispatcher.message(Command("status"))
    async def status(message: Message) -> None:
        current = await runtime.inspect(key_for(message))
        phase = current.idle.phase.value if current is not None else "no activity"
        await message.answer(f"Idle phase: {phase}. Memory storage is lost on restart.")

    @dispatcher.message(F.text == "Draft help")
    async def draft_help(message: Message) -> None:
        await message.answer(
            "Type a draft and leave it idle; the inline question works beside this reply tray."
        )

    @dispatcher.message(F.text)
    async def accept_text(message: Message, idle_context: IdleContext) -> None:
        key = key_for(message)
        activity = await idle_context.current()
        draft = adapter.drafts.get(key)
        if activity is None or draft is None or draft.activity_id != activity.activity_id:
            await message.answer("Use /draft to start the example.")
            return
        draft.text = message.text or ""
        await idle_context.touch(
            expected=activity.guard, operation_id=f"message:{message.message_id}:accept"
        )
        await message.answer(
            "Draft updated. Leave it idle to receive the question.",
            reply_markup=ReplyKeyboardRemove(),
        )

    return dispatcher, runtime


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--controls", choices=["reply", "inline", "commands", "hybrid"], default="inline"
    )
    result.add_argument(
        "--fsm", action="store_true", help="Also track the sample step in aiogram FSM"
    )
    result.add_argument("--after", type=float, default=15, help="Seconds until the question")
    result.add_argument("--grace", type=float, default=30, help="Seconds allowed to answer")
    return result


async def main() -> None:
    args = parser().parse_args()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN in the environment before running the demo")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiogram_idle").setLevel(logging.DEBUG)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    async with Bot(token) as bot:
        dispatcher, _runtime = build_demo(bot, args)
        await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
