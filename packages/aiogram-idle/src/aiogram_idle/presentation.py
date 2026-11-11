"""Telegram prompt presentation, independent of a navigation model."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, time
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .errors import UnsupportedContext
from .models import ActivitySnapshot, IdleConversationKey, MessageRef

if TYPE_CHECKING:
    from .protocols import EffectRecorder


@dataclass(frozen=True)
class PromptTexts:
    question: str = "Do you want to continue?"
    continue_label: str = "Continue"
    cancel_label: str = "Cancel"
    continued: str = "Continuing."
    cancelled: str = "Cancelled."
    timed_out: str = "Cancelled due to inactivity."
    restored: str = "Session restored."
    stale: str = "This prompt is no longer active."
    tray_hint: str = "Choose an action."
    busy: str = "Your previous action is still being processed. Please try again shortly."

    def __post_init__(self) -> None:
        if not self.continue_label or not self.cancel_label:
            raise ValueError("Prompt labels must not be empty")
        if self.continue_label == self.cancel_label:
            raise ValueError("Continue and Cancel labels must be distinct")


@dataclass(frozen=True)
class PromptReceipt:
    prompt_id: str
    messages: tuple[MessageRef, ...] = ()
    shown_at: float = 0.0
    controls: str = "inline"
    locale: str = "en"
    continue_token: str = ""
    cancel_token: str = ""
    key: IdleConversationKey | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))


@dataclass(frozen=True)
class PromptRequest:
    key: IdleConversationKey
    prompt_id: str
    continue_token: str = ""
    cancel_token: str = ""
    controls: str = "inline"
    locale: str = "en"
    silent: bool = False
    bot: Bot | None = None
    activity: ActivitySnapshot | None = None
    now: float = 0.0
    reply_keyboard: ReplyKeyboardMarkup | None = None
    effects: EffectRecorder | None = None


@dataclass(frozen=True)
class FinishRequest:
    receipt: PromptReceipt
    outcome: str
    bot: Bot | None = None


@dataclass(frozen=True)
class DeliveryReceipt:
    messages: tuple[MessageRef, ...] = ()
    unavailable: bool = False


class QuietHoursResolver(Protocol):
    async def __call__(self, key: IdleConversationKey, at: float) -> bool: ...


@dataclass(frozen=True)
class QuietHours:
    """Tenant-selected local quiet interval; handles midnight and DST."""

    timezone: str
    start: time
    end: time

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("Quiet hours use local naive times")
        if self.start == self.end:
            raise ValueError("Quiet hours start and end must differ")

    async def __call__(self, key: IdleConversationKey, at: float) -> bool:
        local = datetime.fromtimestamp(at, ZoneInfo(self.timezone)).time()
        if self.start < self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end


def callback_data(action: str, token: str) -> str:
    value = f"idle:{action}:{token}"
    if not token or len(value.encode("utf-8")) > 64:
        raise ValueError("Invalid idle callback token")
    return value


class TelegramPromptPresenter:
    replay_safe = True
    """Send new questions and edit outcomes; application adapters restore trays.

    A silent message still notifies without sound. Reply and command controls
    refer to the current server-side prompt, not a particular message generation.
    """

    def __init__(
        self,
        bot: Bot | None = None,
        *,
        texts: PromptTexts | Callable[[str], PromptTexts] | None = None,
        quiet_hours: QuietHoursResolver | None = None,
        locale_resolver: Callable[[IdleConversationKey], Awaitable[str]] | None = None,
    ) -> None:
        self.bot = bot
        self._texts = texts or PromptTexts()
        self.quiet_hours = quiet_hours
        self.locale_resolver = locale_resolver

    def texts(self, locale: str) -> PromptTexts:
        return self._texts(locale) if callable(self._texts) else self._texts

    def _bot(self, override: Bot | None = None) -> Bot:
        bot = override or self.bot
        if bot is None:
            raise ValueError("TelegramPromptPresenter needs a Bot")
        return bot

    async def show(self, request: PromptRequest) -> PromptReceipt:
        bot = self._bot(request.bot)
        if bot.id != request.key.bot_id:
            raise UnsupportedContext("Prompt Bot differs from conversation identity")
        locale = await self.locale_resolver(request.key) if self.locale_resolver else request.locale
        if not locale:
            raise ValueError("Resolved prompt locale must not be empty")
        texts = self.texts(locale)
        markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None
        question = texts.question
        if request.controls in {"inline", "hybrid"}:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=texts.continue_label,
                            callback_data=callback_data("c", request.continue_token),
                        ),
                        InlineKeyboardButton(
                            text=texts.cancel_label,
                            callback_data=callback_data("x", request.cancel_token),
                        ),
                    ]
                ]
            )
        elif request.controls == "reply":
            markup = ReplyKeyboardMarkup(
                keyboard=[
                    [
                        KeyboardButton(text=texts.continue_label),
                        KeyboardButton(text=texts.cancel_label),
                    ]
                ],
                resize_keyboard=True,
                one_time_keyboard=False,
            )
        elif request.controls == "commands":
            question += "\n/continue · /cancel"
        else:
            raise ValueError("Unknown idle prompt control transport")
        silent = request.silent
        if self.quiet_hours is not None:
            silent = silent or await self.quiet_hours(request.key, request.now)

        async def send_question() -> dict[str, int | float]:
            message = await bot.send_message(
                request.key.chat_id,
                question,
                reply_markup=markup,
                disable_notification=silent,
                parse_mode=None,
            )
            return {
                "chat_id": message.chat.id,
                "message_id": message.message_id,
                "shown_at": message.date.timestamp(),
            }

        first = (
            await request.effects.run("question-message", send_question)
            if request.effects
            else await send_question()
        )
        refs = [MessageRef(int(first["chat_id"]), int(first["message_id"]))]
        if request.controls == "hybrid" and request.reply_keyboard is not None:

            async def send_tray() -> dict[str, int]:
                tray = await bot.send_message(
                    request.key.chat_id,
                    texts.tray_hint,
                    reply_markup=request.reply_keyboard,
                    disable_notification=silent,
                    parse_mode=None,
                )
                return {"chat_id": tray.chat.id, "message_id": tray.message_id}

            tray = (
                await request.effects.run("question-tray", send_tray)
                if request.effects
                else await send_tray()
            )
            refs.append(MessageRef(tray["chat_id"], tray["message_id"]))
        return PromptReceipt(
            prompt_id=request.prompt_id,
            messages=tuple(refs),
            shown_at=float(first["shown_at"]),
            controls=request.controls,
            locale=locale,
            continue_token=request.continue_token,
            cancel_token=request.cancel_token,
            key=request.key,
        )

    async def finish(self, request: FinishRequest) -> DeliveryReceipt:
        receipt = request.receipt
        if not receipt.messages:
            return DeliveryReceipt(unavailable=True)
        texts = self.texts(receipt.locale)
        text = {
            "continued": texts.continued,
            "cancelled": texts.cancelled,
            "timed_out": texts.timed_out,
            "restored": texts.restored,
        }.get(request.outcome, texts.cancelled)
        ref = receipt.messages[0]
        try:
            await self._bot(request.bot).edit_message_text(
                text,
                chat_id=ref.chat_id,
                message_id=ref.message_id,
                reply_markup=None,
                parse_mode=None,
            )
        except TelegramBadRequest as exc:
            if not _missing_or_unchanged(exc):
                raise
            return DeliveryReceipt(receipt.messages, unavailable=True)
        return DeliveryReceipt(receipt.messages)

    async def strip(self, receipt: PromptReceipt) -> DeliveryReceipt:
        if not receipt.messages or receipt.controls not in {"inline", "hybrid"}:
            return DeliveryReceipt(receipt.messages)
        ref = receipt.messages[0]
        try:
            await self._bot().edit_message_reply_markup(
                chat_id=ref.chat_id,
                message_id=ref.message_id,
                reply_markup=None,
            )
        except TelegramBadRequest as exc:
            if not _missing_or_unchanged(exc):
                raise
            return DeliveryReceipt(receipt.messages, unavailable=True)
        return DeliveryReceipt(receipt.messages)


def _missing_or_unchanged(exc: TelegramBadRequest) -> bool:
    text = str(exc).lower()
    return any(
        part in text
        for part in (
            "message to edit not found",
            "message is not modified",
            "message can't be edited",
        )
    )
