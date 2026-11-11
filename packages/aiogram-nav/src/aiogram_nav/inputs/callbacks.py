"""Conservative acknowledgements for expired or unauthorized inline controls."""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery


async def acknowledge(bot: Bot, callback_id: str, text: str = "") -> None:
    try:
        await bot.answer_callback_query(callback_id, text=text)
    except TelegramAPIError:
        pass


async def stale(bot: Bot, callback: CallbackQuery) -> None:
    # A rejected token does not prove message ownership. In particular, a
    # prepared view may already have been sent but cannot accept controls yet.
    # Committed-view replacement handles cleanup of known tracked references.
    await acknowledge(bot, callback.id, "This screen is no longer active.")
