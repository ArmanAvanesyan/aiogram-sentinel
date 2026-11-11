"""Observational cleanup never overwrites the current reply tray."""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ..errors import ConfigurationError
from ..models import MessageRef
from .base import CleanupRequest, CleanupResult


async def cleanup_inline(request: CleanupRequest, default_bot: Bot | None) -> CleanupResult:
    bot = request.bot or default_bot
    if bot is None or bot.id != request.key.bot_id:
        raise ConfigurationError("Cleanup needs the conversation's bot")
    if request.previous is None:
        return CleanupResult()
    live: set[tuple[int, int]] = (
        {(ref.chat_id, ref.message_id) for ref in request.current.messages}
        if request.current
        else set()
    )
    stripped: list[MessageRef] = []
    unavailable = False
    for ref in request.previous.messages:
        if ref.role == "tray" or (ref.chat_id, ref.message_id) in live:
            continue
        if ref.chat_id != request.key.chat_id:
            raise ConfigurationError("Cleanup reference differs from conversation")
        if request.ensure_owned is not None:
            request.ensure_owned()
        try:
            await bot.edit_message_reply_markup(
                chat_id=ref.chat_id, message_id=ref.message_id, reply_markup=None
            )
        except TelegramAPIError:
            unavailable = True
        else:
            stripped.append(ref)
    return CleanupResult(tuple(stripped), unavailable)
