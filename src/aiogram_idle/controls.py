"""All Telegram control styles enter the same authorized runtime pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .models import IdleConversationKey
from .presentation import PromptReceipt, PromptTexts


@dataclass(frozen=True)
class ControlContext:
    key: IdleConversationKey
    actor_id: int
    transport: str = "commands"
    prompt_id: str | None = None
    token: str | None = None
    message_id: int | None = None
    operation_id: str = ""


@dataclass(frozen=True)
class ControlResult:
    accepted: bool
    outcome: str
    message: str = ""


@dataclass(frozen=True)
class ReplyPromptControls:
    mode: ClassVar[str] = "reply"
    continue_label: str = "Continue"
    cancel_label: str = "Cancel"

    def match(self, text: str) -> Literal["continue", "cancel"] | None:
        if self.continue_label == self.cancel_label:
            raise ValueError("Reply prompt labels must differ")
        if text == self.continue_label:
            return "continue"
        if text == self.cancel_label:
            return "cancel"
        return None


@dataclass(frozen=True)
class InlinePromptControls:
    mode: ClassVar[str] = "inline"

    def match(self, data: str) -> tuple[Literal["continue", "cancel"], str] | None:
        parts = data.split(":", 2)
        if len(parts) != 3 or parts[0] != "idle" or not parts[2]:
            return None
        if parts[1] == "c":
            return "continue", parts[2]
        if parts[1] == "x":
            return "cancel", parts[2]
        return None


@dataclass(frozen=True)
class CommandPromptControls:
    mode: ClassVar[str] = "commands"

    async def match(self, message: Message, bot: Bot) -> Literal["continue", "cancel"] | None:
        if await Command("continue")(message, bot):
            return "continue"
        if await Command("cancel")(message, bot):
            return "cancel"
        return None


class ControlRuntime(Protocol):
    async def current_prompt(self, key: IdleConversationKey) -> PromptReceipt | None: ...
    async def continue_current(self, context: ControlContext) -> ControlResult: ...
    async def cancel_current(self, context: ControlContext) -> ControlResult: ...


async def handle_control(
    runtime: ControlRuntime,
    event: Message | CallbackQuery,
    key: IdleConversationKey,
    *,
    bot: Bot,
    texts: PromptTexts,
    update_id: int,
) -> bool:
    """Return True only when this update belongs to idle controls.

    A bare /cancel without a prompt falls through to the application's cancel
    handler. Ordinary text is reserved only while the active reply tray asks it.
    """
    prompt = await runtime.current_prompt(key)
    if isinstance(event, CallbackQuery):
        data = event.data or ""
        if not data.startswith("idle:"):
            return False
        parsed = InlinePromptControls().match(data)
        if parsed is None:
            await _ack(bot, event.id, texts.stale)
            return True
        action, token = parsed
        context = ControlContext(
            key=key,
            actor_id=event.from_user.id,
            transport="inline",
            prompt_id=prompt.prompt_id if prompt else None,
            token=token,
            message_id=event.message.message_id if event.message else None,
            operation_id=f"update:{update_id}:idle:{action}",
        )
        # Stop Telegram's spinner before a slow application adapter executes.
        known = prompt is not None and token in {prompt.continue_token, prompt.cancel_token}
        await _ack(bot, event.id, "" if known else texts.stale)
        await _dispatch(runtime, action, context)
        # A rejected token proves neither ownership nor obsolescence of its
        # message. Preserve untracked or partially rendered component keyboards.
        return True
    action = await CommandPromptControls().match(event, bot)
    if action == "cancel" and prompt is None:
        return False
    if action == "continue" and prompt is None:
        await bot.send_message(event.chat.id, texts.stale, parse_mode=None)
        return True
    if action is None and prompt is not None and prompt.controls in {"reply", "hybrid"}:
        action = ReplyPromptControls(texts.continue_label, texts.cancel_label).match(
            event.text or ""
        )
        transport = "reply"
    else:
        transport = "commands"
    if action is None:
        return False
    context = ControlContext(
        key=key,
        actor_id=event.from_user.id if event.from_user else 0,
        transport=transport,
        prompt_id=prompt.prompt_id if prompt else None,
        message_id=event.message_id,
        operation_id=f"update:{update_id}:idle:{action}",
    )
    result = await _dispatch(runtime, action, context)
    if not result.accepted:
        await bot.send_message(event.chat.id, result.message or texts.stale, parse_mode=None)
    return True


async def _dispatch(
    runtime: ControlRuntime,
    action: str,
    context: ControlContext,
) -> ControlResult:
    if action == "continue":
        return await runtime.continue_current(context)
    return await runtime.cancel_current(context)


async def _ack(bot: Bot, callback_id: str, text: str) -> None:
    try:
        await bot.answer_callback_query(callback_id, text=text)
    except TelegramAPIError:
        pass  # Expired acknowledgement cannot undo an already committed answer.
