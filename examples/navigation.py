"""Optional combined demo. Set BOT_TOKEN; NAV_REDIS_URL selects Redis storage."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram_nav import (
    CallbackEntry,
    CommandEntry,
    InputBindings,
    Navigation,
    NavigationAction,
    NavigationContext,
    NavigationRegistry,
    Node,
    RenderRequest,
    ReplyEntry,
    ScreenSpec,
    TextPresenter,
    prepare_token,
)

from aiogram_idle import IdleConfig, IdlePolicies, IdleRuntime
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
from aiogram_idle.models import ActionReceipt, FlowContext, FlowEligibility
from aiogram_idle.policies import ExemptPolicy, PromptPolicy
from aiogram_idle.presentation import TelegramPromptPresenter
from aiogram_idle.storage.base import IdleBackend
from aiogram_idle.storage.memory import MemoryIdleBackend


class ExampleBusiness:
    """Real applications supply authorization and idempotent draft cancellation."""

    async def inspect(self, context: FlowContext) -> FlowEligibility:
        return FlowEligibility()

    async def abandon(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        return ActionReceipt(operation_id, "disarm")

    async def resume(self, context: FlowContext, *, operation_id: str) -> ActionReceipt:
        return ActionReceipt(operation_id)

    async def restore(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        return ActionReceipt(operation_id, "disarm")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--style", choices=["reply", "inline", "commands", "hybrid"], default="hybrid"
    )
    options = parser.parse_args()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN in the environment before running the demo")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiogram_idle").setLevel(logging.DEBUG)
    logging.getLogger("aiogram_nav").setLevel(logging.DEBUG)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    bot = Bot(token)
    config = IdleConfig(enabled=True)
    backend: IdleBackend
    if url := os.environ.get("NAV_REDIS_URL"):
        from aiogram.fsm.storage.base import DefaultKeyBuilder
        from aiogram.fsm.storage.redis import RedisStorage

        from aiogram_idle.storage.redis import RedisIdleBackend

        redis_backend = RedisIdleBackend.from_url(url, config=config)
        await redis_backend.initialize()
        backend = redis_backend
        dispatcher = Dispatcher(
            storage=RedisStorage.from_url(url, key_builder=DefaultKeyBuilder(with_bot_id=True)),
            events_isolation=SimpleEventIsolation(),
        )
    else:
        backend = MemoryIdleBackend(config=config)
        dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    business = ExampleBusiness()
    idle = IdleRuntime(
        backend=backend,
        policies=IdlePolicies(
            {"none": ExemptPolicy(), "draft": PromptPolicy(30, 30, options.style)}
        ),
        adapters={"business": business},
        presenter=TelegramPromptPresenter(bot),
    )
    registry = NavigationRegistry(
        roots={"main"},
        nodes=[Node("main", renderer="text"), Node("form", parent="main", renderer="text")],
    )
    integration = NavigationIntegration(
        idle=idle,
        registry=registry,
        policies=NodePolicies(default="none", overrides={"form": "draft"}),
        adapters={"form": business},
    )
    repo = integration.navigation_repository

    async def screen(request: RenderRequest) -> ScreenSpec:
        inline = None
        if options.style in {"inline", "hybrid"}:
            token = await prepare_token(
                repo,
                request.key,
                session_id=request.session_id,
                view_id=request.view_id,
                expires_at=request.expires_at or 0,
                entry_id="menu-inline",
                action=NavigationAction(target="main"),
                operation_id=f"{request.operation_id}:menu",
            )
            inline = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Menu", callback_data=token)]]
            )
        reply = (
            ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Form"), KeyboardButton(text="Menu")]]
            )
            if options.style in {"reply", "hybrid"}
            else None
        )
        return ScreenSpec(
            f"{request.node_id}: /form, /menu. The form asks after 30 seconds idle.",
            inline_keyboard=inline,
            reply_keyboard=reply,
            reply_keyboard_key="main" if reply else None,
        )

    entries: list[CommandEntry | CallbackEntry | ReplyEntry] = [
        CommandEntry("start", command="start", target="main"),
        CommandEntry("form", command="form", target="form"),
        CommandEntry("menu", command="menu", target="main"),
    ]
    if options.style in {"inline", "hybrid"}:
        entries.append(CallbackEntry("menu-inline", "main", target="main"))
    if options.style in {"reply", "hybrid"}:
        entries.extend(
            [
                ReplyEntry("form-reply", text_key="Form", target="form"),
                ReplyEntry("menu-reply", text_key="Menu", target="main"),
            ]
        )
    navigation = Navigation(
        registry=registry,
        repository=repo,
        presenter=TextPresenter({"text": screen}, bot),
        bindings=InputBindings(entries),
        bot=bot,
    )
    integration.install(dispatcher, navigation=navigation)
    router = Router()

    @router.message()
    async def accepted_text(message: Message, nav_context: NavigationContext) -> None:
        record = await idle.inspect(repo.mapping.to_idle(nav_context.key))
        if record and record.activity:
            # Accept only after successful application processing. FSM/business
            # persistence is a separate store and needs its own transactional policy.
            await integration.touch(
                nav_context.key,
                expected=record.activity.guard,
                operation_id=f"message:{message.message_id}",
            )

    dispatcher.include_router(router)
    try:
        await dispatcher.start_polling(bot, close_bot_session=False)  # pyright: ignore[reportUnknownMemberType]
    finally:
        await idle.stop()
        await backend.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
