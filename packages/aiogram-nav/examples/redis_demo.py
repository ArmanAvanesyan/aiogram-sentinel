"""Shared Redis navigation and FSM. Set BOT_TOKEN and NAV_REDIS_URL to run."""

from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message

from aiogram_nav import (
    CommandEntry,
    InputBindings,
    Navigation,
    NavigationContext,
    NavigationRegistry,
    Node,
    RenderRequest,
    ScreenSpec,
    TextPresenter,
)
from aiogram_nav.storage.redis import RedisNavigationRepository


async def main() -> None:
    # Example-only logging; production applications choose their own handlers.
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("aiogram.event").setLevel(logging.INFO)
    repository = await RedisNavigationRepository.from_url(os.environ["NAV_REDIS_URL"])
    storage = RedisStorage.from_url(
        os.environ["NAV_REDIS_URL"], key_builder=DefaultKeyBuilder(with_bot_id=True)
    )
    bot = Bot(os.environ["BOT_TOKEN"])
    dispatcher = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())

    async def screen(request: RenderRequest) -> ScreenSpec:
        return ScreenSpec(f"{request.node_id}: /menu, /panel. Other text updates an FSM draft.")

    nav = Navigation(
        registry=NavigationRegistry(
            roots={"main"},
            nodes=[Node("main", renderer="text"), Node("panel", parent="main", renderer="text")],
        ),
        repository=repository,
        presenter=TextPresenter({"text": screen}, bot),
        bindings=InputBindings(
            [
                CommandEntry("menu", command="menu", target="main"),
                CommandEntry("start", command="start", target="main"),
                CommandEntry("panel", command="panel", target="panel"),
            ]
        ),
    )
    nav.install(dispatcher)
    business = Router()

    @business.message()
    async def draft(message: Message, state: FSMContext, nav_context: NavigationContext) -> None:
        # The full handler holds the distributed conversation lease. For external
        # databases additionally fence writes by their own draft/session version.
        await state.update_data(draft=message.text or "")
        await nav_context.touch()

    dispatcher.include_router(business)
    try:
        await dispatcher.start_polling(bot, close_bot_session=False)  # pyright: ignore[reportUnknownMemberType]
    finally:
        await repository.close()
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
