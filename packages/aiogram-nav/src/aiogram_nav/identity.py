"""Private conversation identity without synthetic updates or hidden defaults."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiogram import Bot
from aiogram.types import CallbackQuery, Message, Update

from .errors import UnsupportedContext
from .models import ConversationKey

IdentityResolver = Callable[[Update, Bot, str], Awaitable[ConversationKey | None]]


async def private_identity(update: Update, bot: Bot, namespace: str) -> ConversationKey | None:
    event = update.event
    if not isinstance(event, (Message, CallbackQuery)):
        return None
    message = event.message if isinstance(event, CallbackQuery) else event
    actor = event.from_user
    if message is None or actor is None or message.chat.type != "private":
        raise UnsupportedContext("Navigation requires an actor-owned private conversation")
    if any(
        getattr(message, field, None)
        for field in (
            "business_connection_id",
            "message_thread_id",
            "direct_messages_topic_id",
            "direct_messages_topic",
        )
    ):
        raise UnsupportedContext(
            "Business and topic navigation require an explicit identity adapter"
        )
    return ConversationKey(namespace, bot.id, message.chat.id, actor.id)
