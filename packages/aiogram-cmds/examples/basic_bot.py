"""Register default command menus and handle /start and /help."""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from aiogram_cmds import setup_commands_auto


def create_dispatcher(bot: Bot) -> Dispatcher:
    dp = Dispatcher()

    async def startup() -> None:
        await setup_commands_auto(bot)

    @dp.message(Command("start", "help"))
    async def welcome(message: Message) -> None:
        await message.answer("Welcome! Use /start or /help.")

    dp.startup.register(startup)
    return dp


async def main() -> None:
    # Logging belongs to the application entry point. Never print the token.
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN before running this example")
    bot = Bot(token)
    try:
        await create_dispatcher(bot).start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
