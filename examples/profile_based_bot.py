"""Application-selected profiles. Menu visibility never grants authorization."""

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
            "start": CommandDef(descriptions={"en": "Welcome"}),
            "join": CommandDef(descriptions={"en": "Enable the demo member menu"}),
            "profile": CommandDef(descriptions={"en": "View demo profile"}),
        },
        profiles={
            "guest": ProfileDef(include=["start", "join"]),
            "member": ProfileDef(include=["start", "profile"]),
        },
        scopes=[ScopeDef(scope="all_private_chats", profile="guest")],
    )


def create_dispatcher(bot: Bot) -> Dispatcher:
    dp = Dispatcher()
    manager = CommandScopeManager(bot, config=create_config())
    members: set[int] = set()  # Demo only: lost on restart, no identity verification.

    @dp.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer("Use /join to try the member menu.")

    @dp.message(Command("join"))
    async def join(message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            return
        # The application chooses the profile; no implicit Flags.user_id exists.
        await manager.update_profile(message.from_user.id, "member")
        members.add(message.from_user.id)
        await message.answer("Demo member menu enabled.")

    @dp.message(Command("profile"))
    async def profile(message: Message) -> None:
        allowed = message.from_user and message.from_user.id in members
        await message.answer("Demo member" if allowed else "Use /join first.")

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
