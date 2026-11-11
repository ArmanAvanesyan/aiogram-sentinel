"""Binding provenance, localized trays, pending renders and native command parsing."""

import pytest
from aiogram import Bot, Router
from aiogram.methods import EditMessageReplyMarkup
from aiogram.types import CallbackQuery, KeyboardButton, ReplyKeyboardMarkup, Update

from aiogram_nav import (
    CommandEntry,
    InputBindings,
    InvalidParameters,
    Navigation,
    NavigationRegistry,
    Node,
    ReplyEntry,
    ScreenSpec,
    TextPresenter,
)
from aiogram_nav.models import ConversationKey
from examples.demo import build_demo, parse_args
from tests.test_dispatcher import harness
from tests.test_examples import ACTOR, BOT_USER, RecordingSession, incoming


async def test_pending_render_blocks_ordinary_business_handlers():
    dispatcher, nav, bot, _ = harness(
        bindings=InputBindings(
            [CommandEntry("refresh", command="refresh", action="refresh", global_action=True)]
        )
    )
    nav.install(dispatcher)
    app = Router()
    business = []

    @app.message()
    async def handler(message):
        business.append(message.text)

    dispatcher.include_router(app)
    context = nav.for_conversation(ConversationKey(nav.namespace, bot.id, 42, 42))
    try:
        await context.go("main", operation_id="main")
        async with nav.coordinator.hold(context.key):
            await context.prepare_render("panel", operation_id="pending")
        await dispatcher.feed_update(bot, Update(update_id=2, message=incoming("business input")))
        assert business == []
        assert (await context.current()).node_id == "main"
        await dispatcher.feed_update(bot, Update(update_id=3, message=incoming("/refresh")))
        assert not await nav.is_busy(context.key)
        await dispatcher.feed_update(bot, Update(update_id=4, message=incoming("accepted")))
        assert business == ["accepted"]
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_native_command_mentions_and_validated_arguments():
    dispatcher, original, bot, session = harness()

    async def screen(request):
        return ScreenSpec(request.node_id)

    def validate(params):
        if not isinstance(params.get("page"), int):
            raise ValueError("page required")
        return params

    nav = Navigation(
        registry=NavigationRegistry(
            roots={"main"},
            nodes=[
                Node("main", renderer="screen"),
                Node("panel", parent="main", renderer="screen", validator=validate),
            ],
        ),
        repository=original.repository,
        presenter=TextPresenter({"screen": screen}, bot),
    )
    nav.bind(
        InputBindings(
            [
                CommandEntry("start", command="start", target="main", global_action=True),
                CommandEntry(
                    "panel",
                    command="panel",
                    target="panel",
                    decoder=lambda cmd: {"page": int(cmd.args or "")},
                ),
            ]
        )
    )
    nav.install(dispatcher)
    app = Router()
    unhandled = []

    @app.message()
    async def fallback(message):
        unhandled.append(message.text)

    dispatcher.include_router(app)
    context = nav.for_conversation(ConversationKey(nav.namespace, bot.id, 42, 42))
    try:
        await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("/start")))
        await dispatcher.feed_update(
            bot, Update(update_id=2, message=incoming("/panel@another_bot 3"))
        )
        assert unhandled == ["/panel@another_bot 3"]
        await dispatcher.feed_update(
            bot, Update(update_id=3, message=incoming("/panel@navigation_demo_bot 3"))
        )
        assert (await context.current()).params == {"page": 3}
        before = len(session.methods)
        with pytest.raises(InvalidParameters):
            await dispatcher.feed_update(
                bot, Update(update_id=4, message=incoming("/panel invalid"))
            )
        assert len(session.methods) == before
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_current_and_installed_reply_locale_only():
    dispatcher, original, bot, _ = harness()
    locale = ["en"]
    labels = {"en": {"panel": "Open", "home": "Back"}, "ru": {"panel": "Открыть", "home": "Назад"}}

    def translator(key, lang):
        return labels[lang][key]

    async def resolve(key):
        return locale[0]

    async def screen(request):
        label = translator("panel" if request.node_id == "main" else "home", request.locale)
        return ScreenSpec(
            request.node_id,
            reply_keyboard=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=label)]]),
            reply_keyboard_key=request.node_id,
        )

    nav = Navigation(
        registry=original.registry,
        repository=original.repository,
        presenter=TextPresenter({"screen": screen}, bot),
        locale_resolver=resolve,
    )
    nav.bind(
        InputBindings(
            [
                ReplyEntry(
                    "open", text_key="panel", target="panel", from_nodes=frozenset({"main"})
                ),
                ReplyEntry("home", text_key="home", action="home", global_action=True),
            ]
        ),
        translator=translator,
    )
    nav.install(dispatcher)
    app = Router()
    fallback = []

    @app.message()
    async def typing(message):
        fallback.append(message.text)

    dispatcher.include_router(app)
    context = nav.for_conversation(ConversationKey(nav.namespace, bot.id, 42, 42))
    try:
        await context.go("main", operation_id="root")
        locale[0] = "ru"
        await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("Open")))
        assert (await context.current()).view.reply_keyboard_locale == "ru"
        await dispatcher.feed_update(bot, Update(update_id=2, message=incoming("Back")))
        assert fallback == ["Back"]
        await dispatcher.feed_update(bot, Update(update_id=3, message=incoming("Назад")))
        assert (await context.current()).node_id == "main"
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_stale_callback_acknowledges_without_repeating_tracked_cleanup():
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    dispatcher, nav = build_demo(bot, parse_args(["--style", "inline"]))
    context = nav.for_conversation(ConversationKey(nav.namespace, bot.id, 42, 42))
    try:
        await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("/start")))
        old = await context.current()
        data = next(
            method.reply_markup.inline_keyboard[0][0].callback_data
            for method in session.methods
            if getattr(method, "reply_markup", None) is not None
        )
        await context.refresh(operation_id="fresh")
        current = await context.current()
        assert current.view.messages[0].message_id != old.view.messages[0].message_id
        callback = CallbackQuery(
            id="stale",
            from_user=ACTOR,
            chat_instance="test",
            data=data,
            message=incoming("old", old.view.messages[0].message_id).model_copy(
                update={"from_user": BOT_USER}
            ),
        )
        before = len(session.methods)
        await dispatcher.feed_update(bot, Update(update_id=2, callback_query=callback))
        assert not any(
            isinstance(method, EditMessageReplyMarkup) for method in session.methods[before:]
        )
        cleanup = [
            method for method in session.methods if isinstance(method, EditMessageReplyMarkup)
        ]
        assert cleanup[-1].message_id == old.view.messages[0].message_id
        assert (await context.current()).view.view_id == current.view.view_id
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_free_typing_can_disable_scoped_reply_navigation():
    dispatcher, original, bot, _ = harness()

    async def screen(request):
        return ScreenSpec(request.node_id)

    nav = Navigation(
        registry=NavigationRegistry(
            roots={"main"},
            nodes=[
                Node("main", renderer="screen"),
                Node(
                    "editor", parent="main", renderer="screen", metadata={"reply_navigation": False}
                ),
            ],
        ),
        repository=original.repository,
        presenter=TextPresenter({"screen": screen}, bot),
    )
    nav.bind(
        InputBindings(
            [
                ReplyEntry("scoped", text_key="Open", target="main"),
                ReplyEntry("global", text_key="Home", action="home", global_action=True),
            ]
        )
    )
    nav.install(dispatcher)
    app = Router()
    accepted = []

    @app.message()
    async def business(message):
        accepted.append(message.text)

    dispatcher.include_router(app)
    context = nav.for_conversation(ConversationKey(nav.namespace, bot.id, 42, 42))
    try:
        await context.go("editor", operation_id="editor")
        await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("Open")))
        assert accepted == ["Open"]
        assert (await context.current()).node_id == "editor"
        await dispatcher.feed_update(bot, Update(update_id=2, message=incoming("Home")))
        assert (await context.current()).node_id == "main"
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
