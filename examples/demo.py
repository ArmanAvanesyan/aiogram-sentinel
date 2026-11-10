"""Run neutral navigation demos. BOT_TOKEN is read only by the CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Sequence
from typing import cast

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from aiogram_nav.config import NavigationConfig
from aiogram_nav.context import NavigationContext
from aiogram_nav.inputs.bindings import CallbackEntry, CommandEntry, InputBindings, ReplyEntry
from aiogram_nav.inputs.tokens import prepare_token
from aiogram_nav.models import ActionKind, ConversationKey, NavigationAction, Node, RenderRequest
from aiogram_nav.navigation import Navigation
from aiogram_nav.registry import NavigationRegistry
from aiogram_nav.rendering.base import ScreenSpec
from aiogram_nav.rendering.text import TextPresenter
from aiogram_nav.storage.memory import MemoryNavigationRepository

LOGGER = logging.getLogger("aiogram_nav_demo")
LABELS = {
    "panel": "Open panel",
    "editor": "Edit draft",
    "back": "Back",
    "home": "Home",
    "cancel": "Cancel",
}


class DraftFlow(StatesGroup):
    typing = State()


def translate(text_key: str, locale: str) -> str:
    """A real application supplies its own translation catalog."""
    return LABELS[text_key]


class DemoScreens:
    def __init__(
        self,
        bot: Bot,
        dispatcher: Dispatcher,
        repository: MemoryNavigationRepository,
        *,
        style: str,
        fsm: bool,
    ) -> None:
        self.bot, self.dispatcher, self.repository = bot, dispatcher, repository
        self.style, self.fsm = style, fsm
        self.drafts: dict[ConversationKey, str] = {}

    async def draft(self, key: ConversationKey) -> str:
        if self.fsm:
            state = self.dispatcher.fsm.get_context(
                bot=self.bot, chat_id=key.chat_id, user_id=key.user_id
            )
            value = (await state.get_data()).get("demo_draft", "")
            return value if isinstance(value, str) else ""
        return self.drafts.get(key, "")

    async def cancel(self, request: RenderRequest) -> dict[str, bool]:
        """Idempotently clear only this application's owned draft fields."""
        if self.fsm:
            state = self.dispatcher.fsm.get_context(
                bot=self.bot, chat_id=request.key.chat_id, user_id=request.key.user_id
            )
            data = await state.get_data()
            data.pop("demo_draft", None)
            await state.set_data(data)
            if await state.get_state() == DraftFlow.typing.state:
                await state.set_state(None)
        else:
            self.drafts.pop(request.key, None)
        return {"draft_cleared": True}

    async def render(self, request: RenderRequest) -> ScreenSpec:
        actions = ["panel", "editor"] if request.node_id == "main" else ["back", "home", "cancel"]
        if request.node_id == "editor":
            text = f"Draft editor: {len(await self.draft(request.key))} saved characters. Type text. Back keeps your draft; Cancel discards it."
        elif request.node_id == "panel":
            text = "Read-only example panel. Use Back or Home."
        else:
            text = "Navigation demo. Open a panel or edit a draft. /status reports safe metadata."
        inline = None
        reply = None
        if self.style in {"inline", "hybrid"}:
            if request.expires_at is None:
                raise RuntimeError("The navigation runtime must supply prepared expiry")
            buttons: list[InlineKeyboardButton] = []
            for action in actions:
                target = action if action in {"panel", "editor"} else None
                kind = "go" if target else action
                data = await prepare_token(
                    self.repository,
                    request.key,
                    session_id=request.session_id,
                    view_id=request.view_id,
                    action=NavigationAction(kind=cast(ActionKind, kind), target=target),
                    expires_at=request.expires_at,
                    operation_id=f"{request.operation_id}:button:{action}",
                    entry_id=f"inline-{action}",
                )
                buttons.append(InlineKeyboardButton(text=LABELS[action], callback_data=data))
            inline = InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons])
        if self.style in {"reply", "hybrid"}:
            # A stable tray avoids a new tray message for each inline refresh.
            reply = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=LABELS[name])] for name in actions],
                resize_keyboard=True,
            )
        if self.style == "commands":
            text += "\n/panel · /edit · /back · /home · /cancel · /refresh"
        return ScreenSpec(
            text=text,
            inline_keyboard=inline,
            reply_keyboard=reply,
            reply_keyboard_key=("demo-main" if request.node_id == "main" else "demo-secondary")
            if reply
            else None,
        )


def bindings(style: str) -> InputBindings:
    entries: list[CommandEntry | ReplyEntry | CallbackEntry] = [
        CommandEntry("start", command="start", target="main", global_action=True)
    ]
    if style == "commands":
        entries.extend(
            [
                CommandEntry("panel", command="panel", target="panel"),
                CommandEntry("editor", command="edit", target="editor"),
                CommandEntry("back", command="back", action="back", global_action=True),
                CommandEntry("home", command="home", action="home", global_action=True),
                CommandEntry("cancel", command="cancel", action="cancel", global_action=True),
                CommandEntry("refresh", command="refresh", action="refresh", global_action=True),
            ]
        )
    if style in {"reply", "hybrid"}:
        entries.extend(
            [
                ReplyEntry(
                    "reply-panel", text_key="panel", target="panel", from_nodes=frozenset({"main"})
                ),
                ReplyEntry(
                    "reply-editor",
                    text_key="editor",
                    target="editor",
                    from_nodes=frozenset({"main"}),
                ),
                ReplyEntry("reply-back", text_key="back", action="back", global_action=True),
                ReplyEntry("reply-home", text_key="home", action="home", global_action=True),
                ReplyEntry("reply-cancel", text_key="cancel", action="cancel", global_action=True),
            ]
        )
    if style in {"inline", "hybrid"}:
        entries.extend(
            [
                CallbackEntry(
                    "inline-panel",
                    action="panel.open",
                    target="panel",
                    from_nodes=frozenset({"main"}),
                ),
                CallbackEntry(
                    "inline-editor",
                    action="editor.open",
                    target="editor",
                    from_nodes=frozenset({"main"}),
                ),
                CallbackEntry("inline-back", action="back", kind="back"),
                CallbackEntry("inline-home", action="home", kind="home"),
                CallbackEntry("inline-cancel", action="cancel", kind="cancel"),
            ]
        )
    return InputBindings(entries)


def build_demo(bot: Bot, args: argparse.Namespace) -> tuple[Dispatcher, Navigation]:
    """Construct the application without polling or making Telegram requests."""
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation() if args.fsm else None)
    config = NavigationConfig(root="main", session_seconds=args.session_seconds)
    repository = MemoryNavigationRepository(config=config)
    screens = DemoScreens(bot, dispatcher, repository, style=args.style, fsm=args.fsm)
    registry = NavigationRegistry(
        roots={"main"},
        nodes=[
            Node("main", renderer="screen", cancel_to="main"),
            Node("panel", parent="main", renderer="screen"),
            Node("editor", parent="main", renderer="screen", metadata={"reply_navigation": False}),
        ],
    )
    navigation = Navigation(
        registry=registry,
        repository=repository,
        presenter=TextPresenter({"screen": screens.render}, bot=bot),
        config=config,
        cancel_hook=screens.cancel,
        bot=bot,
    )
    navigation.bind(bindings(args.style), translator=translate)
    navigation.install(dispatcher)
    application = Router(name="demo-business")

    @application.message(Command("status"))
    async def status(message: Message, nav_context: NavigationContext) -> None:
        current = await nav_context.current()
        text = (
            "No active screen. Send /start."
            if current is None
            else (
                f"Node: {current.node_id}; navigation revision: {current.nav_revision}; "
                f"activity revision: {current.activity_revision}; "
                f"saved characters: {len(await screens.draft(nav_context.key))}."
            )
        )
        await message.answer(text, parse_mode=None)

    @application.message(F.text)
    async def accept_text(
        message: Message, nav_context: NavigationContext, state: FSMContext
    ) -> None:
        current = await nav_context.current()
        if current is None or current.node_id != "editor" or (message.text or "").startswith("/"):
            await message.answer("Use /start and choose a screen.", parse_mode=None)
            return
        if args.fsm:
            await state.set_state(DraftFlow.typing)
            await state.update_data(demo_draft=message.text or "")
        else:
            screens.drafts[nav_context.key] = message.text or ""
        await nav_context.touch(source="draft-input")
        await message.answer("Draft saved. Back preserves it; Cancel discards it.", parse_mode=None)
        LOGGER.debug("Accepted draft input on the editor node")

    dispatcher.include_router(application)
    return dispatcher, navigation


def parse_args(
    argv: Sequence[str] | None = None, *, default_style: str = "commands"
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--style", choices=("reply", "inline", "commands", "hybrid"), default=default_style
    )
    parser.add_argument(
        "--fsm", action="store_true", help="Keep the sample draft in application-owned FSM storage"
    )
    parser.add_argument("--session-seconds", type=float, default=3600)
    return parser.parse_args(argv)


def main(*, default_style: str = "commands") -> None:
    args = parse_args(default_style=default_style)
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN before running the demonstration bot")
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiohttp.client").setLevel(logging.WARNING)

    async def run() -> None:
        bot = Bot(token)
        dispatcher, navigation = build_demo(bot, args)
        try:
            # aiogram's UNSET annotation is unknown to strict type checkers.
            await dispatcher.start_polling(bot, close_bot_session=False)  # pyright: ignore[reportUnknownMemberType]
        finally:
            await navigation.repository.close()
            await dispatcher.fsm.close()
            await bot.session.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
