"""Use compiled gettext catalogs through aiogram's optional i18n integration."""

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.i18n import I18n, SimpleI18nMiddleware
from aiogram.utils.i18n import gettext as _

from aiogram_cmds import (
    CmdsConfig,
    CommandDef,
    CommandScopeManager,
    ProfileDef,
    ScopeDef,
    build_translator_from_i18n,
)


def create_dispatcher(bot: Bot) -> Dispatcher:
    i18n = I18n(path=Path(__file__).parent / "locales", default_locale="en")
    if not {"en", "ru", "es"} <= set(i18n.available_locales):
        raise RuntimeError("Compile example catalogs first; see examples/README.md")
    dp = Dispatcher()
    SimpleI18nMiddleware(i18n).setup(dp)
    config = CmdsConfig(
        languages=["en", "ru", "es"],
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
        },
        profiles={"default": ProfileDef(include=["start", "help"])},
        scopes=[ScopeDef(scope="all_private_chats", profile="default")],
    )
    manager = CommandScopeManager(
        bot, config=config, translator=build_translator_from_i18n(i18n)
    )

    @dp.message(Command("start", "help"))
    async def welcome(message: Message) -> None:
        name = message.from_user.first_name if message.from_user else "friend"
        await message.answer(_("welcome.message").format(name=name))

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
