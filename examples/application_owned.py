"""Public-contract application-owned prepared rendering; --help needs no token."""

import argparse
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram_coordination import TrackedEventIsolation

from aiogram_nav import (
    ApplicationPresenter,
    CleanupRequest,
    CleanupResult,
    MemoryNavigationRepository,
    MessageRef,
    Navigation,
    NavigationContext,
    NavigationRegistry,
    Node,
    RenderRequest,
    RenderResult,
)


class MessageStore:
    """Replace these callbacks with the application's existing message store."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def render_navigation(self, request: RenderRequest) -> RenderResult:
        message = await self.bot.send_message(request.key.chat_id, request.node.id)
        return RenderResult(request.view_id, (MessageRef(message.chat.id, message.message_id),))

    async def cleanup_navigation(self, request: CleanupRequest) -> CleanupResult:
        if request.previous is not None:
            for message in request.previous.messages:
                if request.ensure_owned is not None:
                    request.ensure_owned()
                await self.bot.delete_message(message.chat_id, message.message_id)
        return CleanupResult()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        parser.error("Set BOT_TOKEN to run the example")
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("aiogram_nav").setLevel(logging.DEBUG)
    bot = Bot(token)
    store = MessageStore(bot)
    dispatcher = Dispatcher(events_isolation=TrackedEventIsolation(SimpleEventIsolation()))
    nav = Navigation(
        registry=NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="application")]),
        repository=MemoryNavigationRepository(),
        presenter=ApplicationPresenter(cleanup=store.cleanup_navigation),
    )
    nav.install(dispatcher, bindings_mode="manual", allow_root_handlers=True)

    @dispatcher.message(Command("start"))
    async def start(nav_context: NavigationContext) -> None:
        prepared = await nav_context.prepare_action("home")
        rendered = await store.render_navigation(await nav.request(prepared))
        await nav_context.complete_render(prepared, rendered=rendered)

    try:
        await dispatcher.start_polling(bot, close_bot_session=False)  # pyright: ignore[reportUnknownMemberType]
    finally:
        await nav.close()
        await dispatcher.fsm.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
