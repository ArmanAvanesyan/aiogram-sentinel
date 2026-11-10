"""Switch a private-chat command menu using application-owned session state."""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from aiogram_cmds import (
    CmdsConfig,
    CommandDef,
    CommandScopeManager,
    ProfileDef,
    ScopeDef,
)


def create_config() -> CmdsConfig:
    return CmdsConfig(
        commands={
            "start": CommandDef(descriptions={"en": "Open a demo session"}),
            "finish": CommandDef(descriptions={"en": "Finish the demo session"}),
        },
        profiles={
            "ready": ProfileDef(include=["start"]),
            "active": ProfileDef(include=["finish"]),
        },
        scopes=[ScopeDef(scope="all_private_chats", profile="ready")],
    )


def create_dispatcher(bot: Bot) -> Dispatcher:
    dp = Dispatcher()
    manager = CommandScopeManager(bot, config=create_config())

    @dp.message(Command("start", "finish"))
    async def switch(message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            return
        profile = "active" if message.text == "/start" else "ready"
        await manager.update_profile(message.from_user.id, profile)
        await message.answer(f"Menu switched to {profile}.")

    dp.startup.register(manager.setup_all)
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
