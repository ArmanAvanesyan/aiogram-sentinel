"""Recorded Telegram operations; hybrid markup is always split across sends."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from ..errors import ConfigurationError, RenderFailed
from ..json import JsonObject, freeze_object
from ..models import MessageRef, RenderRequest, RenderResult
from .base import ScreenSpec


def _bot(request: RenderRequest, default: Bot | None) -> Bot:
    bot = request.bot or default
    if bot is None or bot.id != request.key.bot_id:
        raise ConfigurationError("Text presentation needs the conversation's bot")
    return bot


def _reference(receipt: object, chat_id: int, role: Literal["content", "tray"]) -> MessageRef:
    if not isinstance(receipt, Mapping):
        raise ConfigurationError("Recorded message receipt must be an object")
    data = cast(Mapping[str, object], receipt)
    if set(data) != {"chat_id", "message_id"}:
        raise ConfigurationError("Recorded message receipt has unsupported fields")
    chat, message = data["chat_id"], data["message_id"]
    if type(chat) is not int or type(message) is not int or chat != chat_id or message < 1:
        raise ConfigurationError("Recorded message receipt has an invalid conversation or message")
    return MessageRef(chat, message, role)


async def deliver(
    request: RenderRequest, spec: ScreenSpec, default_bot: Bot | None
) -> RenderResult:
    bot = _bot(request, default_bot)
    effects = request.effects
    if effects is None:
        raise ConfigurationError("Text presentation requires a prepared effect recorder")
    previous = request.current.view if request.current is not None else None
    old_key = previous.reply_keyboard_key if previous else None
    old_locale = previous.reply_keyboard_locale if previous else None
    if old_key is not None and old_locale is None:
        old_locale = previous.locale if previous else None
    reply = spec.reply_keyboard
    changed = isinstance(reply, ReplyKeyboardRemove) or (
        isinstance(reply, ReplyKeyboardMarkup)
        and (old_key != spec.reply_keyboard_key or old_locale != request.locale)
    )
    # A request may require a new message to isolate recovery from a late
    # edit of the old view. A screen default cannot weaken that constraint.
    preference = request.delivery if request.delivery != "auto" else spec.delivery
    separate_tray = changed and (spec.inline_keyboard is not None or preference == "edit")
    markup = spec.inline_keyboard
    combined_reply = reply if changed and not separate_tray else None
    content_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | None = (
        combined_reply if combined_reply is not None else markup
    )
    candidate = (
        next(
            (
                ref
                for ref in previous.messages
                if ref.role == "content" and ref.chat_id == request.key.chat_id
            ),
            None,
        )
        if previous
        else None
    )
    use_edit = preference != "send" and candidate is not None and combined_reply is None
    if preference == "edit" and not use_edit:
        raise ConfigurationError("Explicit edit requires a compatible tracked content message")

    async def send_content() -> JsonObject:
        message = await bot.send_message(
            request.key.chat_id,
            spec.text,
            reply_markup=content_markup,
            parse_mode=spec.parse_mode,
            disable_notification=spec.silent,
        )
        return freeze_object({"chat_id": message.chat.id, "message_id": message.message_id})

    if use_edit:
        assert candidate is not None

        async def edit_content() -> JsonObject:
            try:
                await bot.edit_message_text(
                    spec.text,
                    chat_id=candidate.chat_id,
                    message_id=candidate.message_id,
                    reply_markup=markup,
                    parse_mode=spec.parse_mode,
                )
            except TelegramBadRequest as exc:
                description = exc.message.lower()
                if "message is not modified" in description:
                    pass
                elif any(
                    part in description
                    for part in (
                        "message to edit not found",
                        "message can't be edited",
                        "there is no text in the message to edit",
                    )
                ):
                    return freeze_object({"unavailable": True})
                else:
                    raise
            return freeze_object({"chat_id": candidate.chat_id, "message_id": candidate.message_id})

        receipt = await effects.run("text.edit", edit_content, replay_safe=True)
        if not isinstance(cast(object, receipt), Mapping):
            raise ConfigurationError("Recorded edit receipt must be an object")
        if receipt.get("unavailable") is True:
            if set(receipt) != {"unavailable"}:
                raise ConfigurationError("Recorded edit rejection has unsupported fields")
            if preference == "edit":
                raise RenderFailed("The requested content message cannot be edited")
            receipt = await effects.run("text.content", send_content)
    else:
        receipt = await effects.run("text.content", send_content)
    refs = [_reference(receipt, request.key.chat_id, "content")]
    if separate_tray:

        async def send_tray() -> JsonObject:
            message = await bot.send_message(
                request.key.chat_id,
                spec.tray_text,
                reply_markup=reply,
                parse_mode=None,
                disable_notification=spec.silent,
            )
            return freeze_object({"chat_id": message.chat.id, "message_id": message.message_id})

        tray = await effects.run("text.tray", send_tray)
        refs.append(_reference(tray, request.key.chat_id, "tray"))
    elif not changed and previous is not None:
        refs.extend(ref for ref in previous.messages if ref.role == "tray")
    key = (
        spec.reply_keyboard_key
        if changed and isinstance(reply, ReplyKeyboardMarkup)
        else (None if isinstance(reply, ReplyKeyboardRemove) else old_key)
    )
    locale = request.locale if changed and key is not None else (old_locale if key else None)
    return RenderResult(request.view_id, tuple(refs), key, request.locale, locale)
