"""Application-owned router and action policies; token-free --help."""

import argparse
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from aiogram_sentinel import (
    ActionPolicy,
    ErrorConfig,
    Sentinel,
    SentinelConfig,
    SentinelExemptions,
    ThrottleCfg,
)


async def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    root, features = Router(name="application"), Router(name="features")
    root.include_router(features)

    @features.message(CommandStart())
    async def welcome(message: Message) -> None:
        await message.answer("Welcome. Send text to exercise message protection.")

    @features.message()
    async def echo(message: Message) -> None:
        await message.answer("Accepted.")

    await Sentinel.setup(
        dispatcher,
        SentinelConfig(
            bucket_mode="action_kind",
            action_policies={
                "message": ActionPolicy(throttle=ThrottleCfg(5, 10)),
                "command": ActionPolicy(throttle=ThrottleCfg(3, 10)),
                "callback_query": ActionPolicy(throttle=ThrottleCfg(20, 10)),
            },
            exemptions=SentinelExemptions(commands=("start",)),
        ),
        router=root,
        error_config=ErrorConfig(reraise_exceptions=(TimeoutError,)),
    )
    return dispatcher


async def run(token: str) -> None:
    dispatcher = await create_dispatcher()
    bot = Bot(token)
    try:
        await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        await bot.session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        parser.error("Set BOT_TOKEN to run the example")
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("aiogram_sentinel").setLevel(logging.DEBUG)
    asyncio.run(run(token))


if __name__ == "__main__":
    main()
