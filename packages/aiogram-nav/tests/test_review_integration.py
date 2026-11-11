"""Review regressions for verified FSM borrowing and input configuration."""

import asyncio

import pytest
from aiogram import BaseMiddleware, Router
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from aiogram_nav import CommandEntry, ConfigurationError, InputBindings, MemoryCoordinator
from tests.test_dispatcher import harness
from tests.test_examples import incoming
from tests.test_fsm_builder import RedisStorage


@pytest.mark.parametrize(
    "mutation", ["storage", "prefix", "bot", "coordinator", "coordinator_isolation"]
)
async def test_installed_identity_mapping_cannot_change(mutation):
    dispatcher, nav, bot, _ = harness(isolated=True)
    storage = RedisStorage(DefaultKeyBuilder(prefix="initial", with_bot_id=True))
    dispatcher.fsm.storage = storage
    nav.install(dispatcher)
    if mutation == "storage":
        dispatcher.fsm.storage = MemoryStorage()
    elif mutation == "prefix":
        storage.key_builder = DefaultKeyBuilder(prefix="changed", with_bot_id=True)
    elif mutation == "bot":
        storage.key_builder = DefaultKeyBuilder(with_bot_id=False)
    elif mutation == "coordinator_isolation":
        from aiogram.fsm.storage.memory import SimpleEventIsolation

        nav.coordinator.isolation = SimpleEventIsolation()
    else:
        # Direct replacement bypassing bind_coordinator is still rejected at use.
        nav.repository.coordinator = MemoryCoordinator()
    try:
        with pytest.raises(ConfigurationError):
            await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("input")))
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_missing_fsm_context_is_rejected_instead_of_recursively_locking():
    dispatcher, nav, bot, _ = harness(isolated=True)

    class RemoveState(BaseMiddleware):
        async def __call__(self, handler, event, data):
            data.pop("state", None)
            return await handler(event, data)

    dispatcher.update.outer_middleware(RemoveState())
    nav.install(dispatcher)
    try:
        with pytest.raises(ConfigurationError):
            await asyncio.wait_for(
                dispatcher.feed_update(bot, Update(update_id=1, message=incoming("input"))),
                timeout=2,
            )
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_binding_router_cannot_be_moved_behind_business_router():
    dispatcher, nav, bot, _ = harness(
        bindings=InputBindings([CommandEntry("main", command="menu", target="main")])
    )
    nav.install(dispatcher)
    business = Router()

    @business.message()
    async def handler(message):
        raise AssertionError("must not admit an input with changed binding precedence")

    dispatcher.include_router(business)
    dispatcher.sub_routers.reverse()
    try:
        with pytest.raises(ConfigurationError):
            await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("/menu")))
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_old_display_locale_is_not_an_installed_reply_tray():
    from aiogram_nav import Navigation, ReplyEntry
    from tests.test_examples import ACTOR

    dispatcher, original, bot, _ = harness()
    locale = ["en"]

    async def resolve(key):
        return locale[0]

    labels = {"en": "Open", "ru": "Открыть"}
    nav = Navigation(
        registry=original.registry,
        repository=original.repository,
        presenter=original.presenter,
        locale_resolver=resolve,
    )
    nav.bind(
        InputBindings([ReplyEntry("open", text_key="open", target="panel")]),
        translator=lambda key, language: labels[language],
    )
    nav.install(dispatcher)
    app = Router()
    received = []

    @app.message()
    async def business(message):
        received.append(message.text)

    dispatcher.include_router(app)
    from aiogram_nav import ConversationKey

    context = nav.for_conversation(ConversationKey(nav.namespace, bot.id, ACTOR.id, ACTOR.id))
    try:
        await context.go("main", operation_id="main")
        assert (await context.current()).view.reply_keyboard_key is None
        locale[0] = "ru"
        await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("Open")))
        assert received == ["Open"]
        assert (await context.current()).node_id == "main"
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_unsupported_direct_topic_context_is_not_silently_collapsed():
    from aiogram_nav import UnsupportedContext

    dispatcher, nav, bot, _ = harness()
    nav.install(dispatcher)
    from aiogram import types

    topic_type = getattr(types, "DirectMessagesTopic", None)
    topic = topic_type(topic_id=1) if topic_type is not None else {"topic_id": 1}
    message = incoming("input").model_copy(update={"direct_messages_topic": topic})
    try:
        with pytest.raises(UnsupportedContext):
            await dispatcher.feed_update(bot, Update(update_id=1, message=message))
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_injected_fsm_context_cannot_borrow_another_storages_lock():
    from aiogram.fsm.context import FSMContext

    dispatcher, nav, bot, _ = harness(isolated=True)

    class ReplaceContext(BaseMiddleware):
        async def __call__(self, handler, event, data):
            actual = data["state"]
            data["state"] = FSMContext(storage=MemoryStorage(), key=actual.key)
            return await handler(event, data)

    dispatcher.update.outer_middleware(ReplaceContext())
    nav.install(dispatcher)
    try:
        with pytest.raises(ConfigurationError):
            await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("input")))
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_identity_resolver_can_explicitly_skip_navigation_bindings():
    from aiogram.types import CallbackQuery

    from aiogram_nav import CallbackEntry
    from tests.test_examples import ACTOR, BOT_USER

    dispatcher, nav, bot, _ = harness(
        bindings=InputBindings(
            [
                CommandEntry("main", command="menu", target="main"),
                CallbackEntry("open", action="open", target="panel"),
            ]
        )
    )

    async def skip(update, actual_bot, namespace):
        return None

    nav.identity = skip
    nav.install(dispatcher)
    app = Router()
    handled = []

    @app.message()
    async def message(message):
        handled.append("message")

    @app.callback_query()
    async def callback(callback):
        handled.append("callback")

    dispatcher.include_router(app)
    try:
        await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("/menu")))
        query = CallbackQuery(
            id="other-context",
            from_user=ACTOR,
            chat_instance="test",
            message=incoming("other").model_copy(update={"from_user": BOT_USER}),
            data="nav:AAAAAAAAAAAAAAAAAAAA",
        )
        await dispatcher.feed_update(bot, Update(update_id=2, callback_query=query))
        assert handled == ["message", "callback"]
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
